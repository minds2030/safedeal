// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title SafeDeal Escrow V2
 * @notice Escrow for digital service deals on Telegram
 * @dev Channel owner sets their own fee. Works on any EVM chain.
 */
contract SafeDealEscrow is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;

    // ── Constants ─────────────────────────────────────────────
    uint256 public constant PLATFORM_FEE_BPS   = 200;   // 2% fixed
    uint256 public constant MAX_CHANNEL_FEE_BPS = 1000; // 10% max
    uint256 public constant BPS_DENOM          = 10000;
    uint256 public constant MIN_GUARANTEE      = 1 hours;
    uint256 public constant MAX_GUARANTEE      = 30 days;

    // ── Enums ─────────────────────────────────────────────────
    enum Status {
        PENDING_PAYMENT,  // 0
        FUNDED,           // 1
        DELIVERED,        // 2
        COMPLETED,        // 3
        DISPUTED,         // 4
        REFUNDED,         // 5
        CANCELLED         // 6
    }

    // ── Structs ───────────────────────────────────────────────
    struct Deal {
        uint256 id;
        address seller;
        address buyer;
        address token;          // address(0) = native coin
        uint256 amount;
        uint256 sellerReceives;
        uint256 platformFee;
        uint256 channelFee;
        address channelWallet;
        uint256 channelFeeBps;  // stored per-deal so it can't change after creation
        uint256 guaranteeEnd;
        Status  status;
        string  description;
        uint256 createdAt;
    }

    struct ChannelConfig {
        uint256 feeBps;         // channel commission in BPS
        address wallet;         // where fees go
        bool    canArbitrate;   // can resolve disputes
        bool    exists;
    }

    // ── State ─────────────────────────────────────────────────
    uint256 public nextDealId = 1;
    address public platformWallet;

    mapping(uint256 => Deal)          public deals;
    mapping(address => ChannelConfig) public channels;  // channelWallet → config
    mapping(address => bool)          public arbitrators;
    mapping(address => uint256[])     public sellerDeals;
    mapping(address => uint256[])     public buyerDeals;

    // ── Events ────────────────────────────────────────────────
    event DealCreated(uint256 indexed id, address indexed seller, address indexed buyer, uint256 amount);
    event DealFunded(uint256 indexed id);
    event DealDelivered(uint256 indexed id);
    event DealCompleted(uint256 indexed id);
    event DealDisputed(uint256 indexed id, address by);
    event DealResolved(uint256 indexed id, address winner, uint256 sellerAmt, uint256 buyerAmt);
    event DealCancelled(uint256 indexed id);
    event ChannelConfigured(address indexed channelWallet, uint256 feeBps);

    // ── Modifiers ─────────────────────────────────────────────
    modifier onlySeller(uint256 id) {
        require(deals[id].seller == msg.sender, "Not seller");
        _;
    }
    modifier onlyBuyer(uint256 id) {
        require(deals[id].buyer == msg.sender, "Not buyer");
        _;
    }
    modifier onlyParty(uint256 id) {
        require(
            deals[id].seller == msg.sender || deals[id].buyer == msg.sender,
            "Not a party"
        );
        _;
    }
    modifier onlyArbitrator() {
        require(arbitrators[msg.sender] || msg.sender == owner(), "Not arbitrator");
        _;
    }
    modifier inStatus(uint256 id, Status s) {
        require(deals[id].status == s, "Wrong status");
        _;
    }

    // ── Constructor ───────────────────────────────────────────
    constructor(address _platformWallet) Ownable(msg.sender) {
        platformWallet = _platformWallet;
        arbitrators[msg.sender] = true;
    }

    // ══════════════════════════════════════════════════════════
    // CHANNEL OWNER FUNCTIONS
    // ══════════════════════════════════════════════════════════

    /**
     * @notice Channel owner registers their channel config
     * @param feeBps Their commission (0-1000 = 0%-10%)
     */
    function configureChannel(uint256 feeBps) external {
        require(feeBps <= MAX_CHANNEL_FEE_BPS, "Fee too high (max 10%)");
        channels[msg.sender] = ChannelConfig({
            feeBps:       feeBps,
            wallet:       msg.sender,
            canArbitrate: true,
            exists:       true
        });
        // Register as arbitrator automatically
        arbitrators[msg.sender] = true;
        emit ChannelConfigured(msg.sender, feeBps);
    }

    /**
     * @notice Update channel fee only
     */
    function updateChannelFee(uint256 feeBps) external {
        require(channels[msg.sender].exists, "Channel not configured");
        require(feeBps <= MAX_CHANNEL_FEE_BPS, "Fee too high");
        channels[msg.sender].feeBps = feeBps;
        emit ChannelConfigured(msg.sender, feeBps);
    }

    /**
     * @notice Get channel fee for a wallet
     */
    function getChannelFee(address channelWallet) external view returns (uint256) {
        return channels[channelWallet].feeBps;
    }

    // ══════════════════════════════════════════════════════════
    // CORE DEAL FUNCTIONS
    // ══════════════════════════════════════════════════════════

    /**
     * @notice Create a new escrow deal
     * @param buyer          Buyer's wallet address
     * @param token          ERC20 token (address(0) for native coin)
     * @param amount         Gross amount buyer pays
     * @param guaranteeSecs  Guarantee period in seconds
     * @param channelWallet  Channel owner's wallet
     * @param description    Deal description
     */
    function createDeal(
        address buyer,
        address token,
        uint256 amount,
        uint256 guaranteeSecs,
        address channelWallet,
        string calldata description
    ) external returns (uint256 dealId) {
        require(buyer != address(0) && buyer != msg.sender, "Invalid buyer");
        require(amount > 0, "Amount must be > 0");
        require(
            guaranteeSecs >= MIN_GUARANTEE && guaranteeSecs <= MAX_GUARANTEE,
            "Invalid guarantee period"
        );

        // Get channel fee (0 if channel not configured)
        uint256 chFeeBps = channels[channelWallet].exists
            ? channels[channelWallet].feeBps
            : 0;

        uint256 platFee   = (amount * PLATFORM_FEE_BPS) / BPS_DENOM;
        uint256 chanFee   = (amount * chFeeBps) / BPS_DENOM;
        uint256 sellerAmt = amount - platFee - chanFee;

        dealId = nextDealId++;

        deals[dealId] = Deal({
            id:             dealId,
            seller:         msg.sender,
            buyer:          buyer,
            token:          token,
            amount:         amount,
            sellerReceives: sellerAmt,
            platformFee:    platFee,
            channelFee:     chanFee,
            channelWallet:  channelWallet,
            channelFeeBps:  chFeeBps,
            guaranteeEnd:   0,
            status:         Status.PENDING_PAYMENT,
            description:    description,
            createdAt:      block.timestamp
        });

        sellerDeals[msg.sender].push(dealId);
        buyerDeals[buyer].push(dealId);

        emit DealCreated(dealId, msg.sender, buyer, amount);
    }

    /**
     * @notice Buyer funds the deal — locks money in contract
     */
    function fundDeal(uint256 dealId)
        external payable nonReentrant
        onlyBuyer(dealId)
        inStatus(dealId, Status.PENDING_PAYMENT)
    {
        Deal storage d = deals[dealId];

        if (d.token == address(0)) {
            require(msg.value == d.amount, "Wrong ETH amount");
        } else {
            require(msg.value == 0, "Don't send ETH for token deals");
            IERC20(d.token).safeTransferFrom(msg.sender, address(this), d.amount);
        }

        d.status      = Status.FUNDED;
        d.guaranteeEnd = block.timestamp + _getGuaranteeSecs(dealId);

        emit DealFunded(dealId);
    }

    /**
     * @notice Seller marks service as delivered
     */
    function markDelivered(uint256 dealId)
        external onlySeller(dealId)
        inStatus(dealId, Status.FUNDED)
    {
        deals[dealId].status = Status.DELIVERED;
        emit DealDelivered(dealId);
    }

    /**
     * @notice Buyer confirms receipt — releases funds immediately
     */
    function confirmReceipt(uint256 dealId)
        external nonReentrant onlyBuyer(dealId)
    {
        Deal storage d = deals[dealId];
        require(
            d.status == Status.FUNDED || d.status == Status.DELIVERED,
            "Cannot confirm"
        );
        _releaseFunds(dealId);
    }

    /**
     * @notice Auto-release after guarantee period — anyone can call
     */
    function autoRelease(uint256 dealId) external nonReentrant {
        Deal storage d = deals[dealId];
        require(
            d.status == Status.FUNDED || d.status == Status.DELIVERED,
            "Cannot auto-release"
        );
        require(block.timestamp >= d.guaranteeEnd, "Guarantee period active");
        _releaseFunds(dealId);
    }

    /**
     * @notice Open a dispute
     * @dev Buyer can dispute anytime; seller only after guarantee ends
     */
    function openDispute(uint256 dealId)
        external onlyParty(dealId)
    {
        Deal storage d = deals[dealId];
        require(
            d.status == Status.FUNDED || d.status == Status.DELIVERED,
            "Cannot dispute"
        );
        if (msg.sender == d.seller) {
            require(block.timestamp >= d.guaranteeEnd, "Wait for guarantee period");
        }
        d.status = Status.DISPUTED;
        emit DealDisputed(dealId, msg.sender);
    }

    /**
     * @notice Arbitrator resolves dispute
     * @param sellerPct Percentage to seller (0-100)
     *        100 = full release to seller
     *        0   = full refund to buyer
     *        50  = split equally
     */
    function resolveDispute(uint256 dealId, uint256 sellerPct)
        external nonReentrant onlyArbitrator
        inStatus(dealId, Status.DISPUTED)
    {
        require(sellerPct <= 100, "Invalid percentage");
        Deal storage d = deals[dealId];

        uint256 toSeller;
        uint256 toBuyer;

        if (sellerPct == 0) {
            // Full refund
            toBuyer  = d.amount;
            toSeller = 0;
            d.status = Status.REFUNDED;
        } else if (sellerPct == 100) {
            // Full release
            toSeller = d.sellerReceives;
            toBuyer  = 0;
            d.status = Status.COMPLETED;
        } else {
            // Split
            toSeller = (d.sellerReceives * sellerPct) / 100;
            toBuyer  = d.amount - toSeller
                       - d.platformFee
                       - d.channelFee;
            d.status = Status.COMPLETED;
        }

        _transfer(d.token, d.seller, toSeller);
        _transfer(d.token, d.buyer,  toBuyer);

        if (sellerPct > 0) {
            _transfer(d.token, platformWallet,  d.platformFee);
            if (d.channelFee > 0)
                _transfer(d.token, d.channelWallet, d.channelFee);
        }

        emit DealResolved(dealId,
            sellerPct > 0 ? d.seller : d.buyer,
            toSeller, toBuyer
        );
    }

    /**
     * @notice Cancel deal before funding
     */
    function cancelDeal(uint256 dealId)
        external onlySeller(dealId)
        inStatus(dealId, Status.PENDING_PAYMENT)
    {
        deals[dealId].status = Status.CANCELLED;
        emit DealCancelled(dealId);
    }

    // ══════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ══════════════════════════════════════════════════════════

    function getDeal(uint256 dealId) external view returns (Deal memory) {
        return deals[dealId];
    }

    function getSellerDeals(address seller) external view returns (uint256[] memory) {
        return sellerDeals[seller];
    }

    function getBuyerDeals(address buyer) external view returns (uint256[] memory) {
        return buyerDeals[buyer];
    }

    function isExpired(uint256 dealId) external view returns (bool) {
        Deal storage d = deals[dealId];
        return d.guaranteeEnd > 0 && block.timestamp >= d.guaranteeEnd;
    }

    function getStatus(uint256 dealId) external view returns (uint8) {
        return uint8(deals[dealId].status);
    }

    // ══════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS
    // ══════════════════════════════════════════════════════════

    function setPlatformWallet(address newWallet) external onlyOwner {
        platformWallet = newWallet;
    }

    function addArbitrator(address arb) external onlyOwner {
        arbitrators[arb] = true;
    }

    function removeArbitrator(address arb) external onlyOwner {
        arbitrators[arb] = false;
    }

    // ══════════════════════════════════════════════════════════
    // INTERNAL
    // ══════════════════════════════════════════════════════════

    function _releaseFunds(uint256 dealId) internal {
        Deal storage d = deals[dealId];
        d.status = Status.COMPLETED;

        _transfer(d.token, d.seller,        d.sellerReceives);
        _transfer(d.token, platformWallet,   d.platformFee);
        if (d.channelFee > 0)
            _transfer(d.token, d.channelWallet, d.channelFee);

        emit DealCompleted(dealId);
    }

    function _transfer(address token, address to, uint256 amount) internal {
        if (amount == 0 || to == address(0)) return;
        if (token == address(0)) {
            (bool ok,) = payable(to).call{value: amount}("");
            require(ok, "Transfer failed");
        } else {
            IERC20(token).safeTransfer(to, amount);
        }
    }

    function _getGuaranteeSecs(uint256 dealId) internal view returns (uint256) {
        // Default 24h — can be extended in V3 to store per-deal
        return 24 hours;
    }
}
