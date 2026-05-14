require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: "0.8.20",
  networks: {
    bsc_testnet: {
      url: "https://data-seed-prebsc-1-s1.binance.org:8545",
      chainId: 97,
      accounts: ["356a4597d6ab1724a177daf99aa8347468c6684f075a9213c7db0d11432b1493"]
    }
  }
};