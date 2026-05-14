const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying with:", deployer.address);

  const Escrow = await hre.ethers.getContractFactory("SafeDealEscrow");
  const escrow = await Escrow.deploy(deployer.address);
  await escrow.waitForDeployment();

  console.log("✅ Contract deployed to:", await escrow.getAddress());
}

main().catch(console.error);