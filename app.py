from flask import Flask, render_template, request, jsonify, redirect, url_for
from xrpl.models.requests import AccountInfo
from xrpl.wallet import generate_faucet_wallet, Wallet
import xrpl
from xrpl.models.transactions import Payment
from xrpl.transaction import sign, autofill, submit_and_wait
from datetime import datetime, timedelta
import json  # For JSON serialization


app = Flask(__name__)

global_temp_address = ""
global_temp_seed = ""
global_transactions = []  # Global variable to store transaction history

xrp_jpy = 330

# Store wallet details for display
wallet_details = {}

# Helper function to generate a new XRP wallet on the testnet
def create_wallet():
    testnet_client = xrpl.clients.JsonRpcClient("https://s.altnet.rippletest.net:51234/")
    wallet = generate_faucet_wallet(testnet_client)
    print("wallet: ", wallet)

    # Fetch the wallet balance using account_info request
    account_info = AccountInfo(
        account=wallet.classic_address,
        ledger_index="validated",
        strict=True
    )
    response = testnet_client.request(account_info)
    balance = float(response.result["account_data"]["Balance"]) / 1_000_000  # Convert drops to XRP

    return {
        "address": wallet.classic_address,
        "seed": wallet.seed,
        "balance": balance,
    }

# Helper function to send XRP from one wallet to another
def send_xrp(source_seed, destination_address, amount):
    testnet_client = xrpl.clients.JsonRpcClient("https://s.altnet.rippletest.net:51234/")
    # Create Wallet using seed and derive public/private keys
    source_wallet = Wallet.from_seed(source_seed)
    print("----- source_wallet: ", source_wallet)
    
    payment = Payment(
        account=source_wallet.classic_address,
        destination=destination_address,
        amount=xrpl.utils.xrp_to_drops(amount),
    )
    print("----- Payment: ", payment)

    # Autofill the transaction to fill required fields
    autofilled_tx = autofill(payment, testnet_client)
    print("----- autofilled_tx: ", autofilled_tx)

    # Sign the transaction with the wallet's private key
    signed_tx = sign(autofilled_tx, source_wallet)
    print("----- signed_tx: ", signed_tx)

    # Submit the transaction and wait for the response
    response = submit_and_wait(signed_tx, testnet_client)
    return response

@app.route('/')
def home():
    return render_template("home.html", wallet_details=wallet_details, global_temp_address=global_temp_address, global_temp_seed=global_temp_seed)

@app.route("/merchant")
def merchant():
    return render_template("merchant.html", wallet_details=wallet_details, global_temp_address=global_temp_address, global_temp_seed=global_temp_seed, transactions=global_transactions)

@app.route('/create_wallet', methods=['GET'])
def create_wallet_route():
    global wallet_details, global_temp_address, global_temp_seed
    wallet_details = create_wallet()
    global_temp_address = wallet_details["address"]
    global_temp_seed = wallet_details["seed"]
    return redirect(url_for("home"))


import json  # For JSON serialization

@app.route('/send_xrp', methods=['POST'])
def send_xrp_route():
    global wallet_details, global_temp_address, global_temp_seed, global_transactions

    try:
        source_seed = global_temp_seed
        destination_address = request.form["destination_address"]
        amount = float(request.form["amount"]) / xrp_jpy

        # Perform the transaction
        response = send_xrp(source_seed, destination_address, amount)
        print("Payment Succeeded:", response.result)

        # Fetch updated balance for the wallet
        testnet_client = xrpl.clients.JsonRpcClient("https://s.altnet.rippletest.net:51234/")
        account_info = AccountInfo(
            account=wallet_details["address"],
            ledger_index="validated",
            strict=True
        )
        account_response = testnet_client.request(account_info)
        wallet_details["balance"] = float(account_response.result["account_data"]["Balance"]) / 1_000_000  # Update balance in XRP

        # Transaction time
        ripple_epoch = datetime(2000, 1, 1, 0, 0, 0)
        txn_time_seconds = response.result["tx_json"].get("date", 0)
        txn_time = ripple_epoch + timedelta(seconds=txn_time_seconds)

        # Add transaction to global transaction history
        transaction = {
            "id": response.result["hash"],
            "recipient": destination_address,
            "jpyamount": round(amount*xrp_jpy,1),
            "amount": round(amount,3),
            "fee": float(response.result['tx_json']['Fee']) / 1_000_000,
            "timestamp": txn_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
            "details": response.result,  # Store the entire response JSON
        }
        global_transactions.append(transaction)

        # Pass transactions details as JSON for frontend
        transactions_details_json = json.dumps([tx["details"] for tx in global_transactions])

        # Success message
        message = (
            f"Transaction Complete! Transaction Amount: {amount} XRP, "
            f"Fee: {float(response.result['tx_json']['Fee']) / 1_000_000} XRP, "
            f"Transaction ID: {response.result['hash']}, "
            f"Transaction Time: {txn_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        print("----- Banner Message: ", message)
        return render_template("merchant.html", 
                               wallet_details=wallet_details, 
                               global_temp_address=global_temp_address, 
                               global_temp_seed=global_temp_seed, 
                               message=message, 
                               transactions=global_transactions, 
                               transactions_details_json=transactions_details_json)

    except Exception as e:
        print("Error:", str(e))
        return render_template("merchant.html", 
                               wallet_details=wallet_details, 
                               error=str(e), 
                               transactions=global_transactions, 
                               transactions_details_json=json.dumps([tx["details"] for tx in global_transactions]))


if __name__ == '__main__':
    app.run(debug=True)
