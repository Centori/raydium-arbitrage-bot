from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solana.rpc.types import TxOpts
from solana.system_program import transfer, TransferParams
from solana.rpc.commitment import Confirmed
import os
from dotenv import load_dotenv
import base58
import binascii
from config import Config
import asyncio

async def run_basic_transaction():
    # Load environment and config
    config = Config()
    
    # Initialize Solana client
    client = AsyncClient(config.RPC_ENDPOINT)
    
    # Load private key from environment
    load_dotenv()
    private_key = os.getenv('SOLANA_PRIVATE_KEY')
    if not private_key:
        raise ValueError("No private key found in environment")
    
    # Load keypair from private key
    try:
        # Try base58 first
        private_key_bytes = base58.b58decode(private_key)
        sender = Keypair.from_secret_key(private_key_bytes)
    except:
        try:
            # Try hex format
            private_key_bytes = binascii.unhexlify(private_key)
            sender = Keypair.from_secret_key(private_key_bytes)
        except:
            raise ValueError("Invalid private key format")
    
    # Set up receiver (using system program address as example)
    receiver = PublicKey("11111111111111111111111111111111")
    
    print(f"Sender pubkey: {sender.public_key}")
    print(f"Receiver pubkey: {receiver}")
    
    try:
        # Get initial balances
        sender_balance_resp = await client.get_balance(sender.public_key, commitment=Confirmed)
        receiver_balance_resp = await client.get_balance(receiver, commitment=Confirmed)
        sender_balance = sender_balance_resp['result']['value']
        receiver_balance = receiver_balance_resp['result']['value']
        print(f"Initial sender balance: {sender_balance / 1e9} SOL")
        print(f"Initial receiver balance: {receiver_balance / 1e9} SOL")
        
        # Create recent blockhash
        blockhash_resp = await client.get_latest_blockhash(commitment=Confirmed)
        recent_blockhash = blockhash_resp['result']['value']['blockhash']
        
        # Create a simple SOL transfer transaction
        transfer_ix = transfer(
            TransferParams(
                from_pubkey=sender.public_key,
                to_pubkey=receiver,
                lamports=1000  # 0.000001 SOL
            )
        )
        
        tx = Transaction().add(transfer_ix)
        tx.recent_blockhash = recent_blockhash
        tx.sign(sender)
        
        # Send transaction
        result = await client.send_transaction(tx, opts=TxOpts(skip_preflight=False))
        print(f"Transaction sent! Signature: {result['result']}")
        
        # Wait a bit for confirmation
        await asyncio.sleep(2)
        
        # Get final balances
        sender_balance_resp = await client.get_balance(sender.public_key, commitment=Confirmed)
        receiver_balance_resp = await client.get_balance(receiver, commitment=Confirmed)
        sender_balance = sender_balance_resp['result']['value']
        receiver_balance = receiver_balance_resp['result']['value']
        print(f"Final sender balance: {sender_balance / 1e9} SOL")
        print(f"Final receiver balance: {receiver_balance / 1e9} SOL")
        
    except Exception as e:
        print(f"Error sending transaction: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(run_basic_transaction())