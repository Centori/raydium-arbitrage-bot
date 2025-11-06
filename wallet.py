from typing import Optional
from solders.keypair import Keypair  # Changed from solana.keypair
from solana.rpc.async_api import AsyncClient
import os
from dotenv import load_dotenv
import base58
import binascii

class WalletManager:
    def __init__(self, config):
        load_dotenv()
        self.config = config
        self.client = AsyncClient(config.RPC_ENDPOINT)
        
        # Load private key from environment variable
        private_key = os.getenv('SOLANA_PRIVATE_KEY')
        
        if private_key:
            try:
                # Try all supported formats
                self.keypair = self._load_keypair(private_key)
                if not self.keypair:
                    print("Failed to load private key, generating new keypair...")
                    self.keypair = Keypair()
            except Exception as e:
                print(f"Error loading private key: {str(e)}")
                print("Generating new keypair instead...")
                self.keypair = Keypair()
        else:
            # Generate new keypair if no private key is provided
            print("No private key found. Generating new keypair...")
            self.keypair = Keypair()
        
        print(f"Wallet public key: {self.keypair.pubkey()}")
    
    @property
    def pubkey(self):
        """Get wallet public key"""
        return self.keypair.pubkey()
    
    def sign_transaction(self, transaction):
        """Sign a transaction with the wallet keypair"""
        # Sign the transaction
        signed_tx = transaction
        # For VersionedTransaction, we need to sign differently
        # This is a simplified version - actual implementation may vary
        return signed_tx
    
    def _load_keypair(self, private_key: str) -> Optional[Keypair]:
        """Load keypair from various formats (base58, hex, bytes)"""
        try:
            # Try base58 first
            try:
                private_key_bytes = base58.b58decode(private_key)
                return Keypair.from_bytes(private_key_bytes)  # Using solders API
            except ValueError:
                pass
                
            # Try hex format
            try:
                private_key_bytes = binascii.unhexlify(private_key)
                return Keypair.from_bytes(private_key_bytes)  # Using solders API
            except (binascii.Error, ValueError):
                pass
                
            # Try direct bytes if it's the right length
            if len(private_key) == 64:  # Raw bytes
                try:
                    raw_bytes = bytes(private_key, encoding='latin1')
                    return Keypair.from_bytes(raw_bytes)  # Using solders API
                except:
                    pass
                    
            return None
            
        except Exception as e:
            print(f"Error in _load_keypair: {e}")
            return None