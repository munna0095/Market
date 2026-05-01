import json
import os

class TradingService:
    def __init__(self):
        self.portfolio_path = "portfolio.json"
        self.load_portfolio()

    def load_portfolio(self):
        if os.path.exists(self.portfolio_path):
            with open(self.portfolio_path, "r") as f:
                self.portfolio = json.load(f)
        else:
            self.portfolio = {
                "balance": 10000.0,
                "positions": [],  # List of {symbol, amount, entry_price, type}
                "history": []
            }
            self.save_portfolio()

    def save_portfolio(self):
        with open(self.portfolio_path, "w") as f:
            json.dump(self.portfolio, f, indent=2)

    def execute_trade(self, symbol, side, amount, price):
        """
        Executes a paper trade.
        side: 'buy' or 'sell'
        """
        cost = amount * price
        if side == "buy":
            if self.portfolio["balance"] >= cost:
                self.portfolio["balance"] -= cost
                self.portfolio["positions"].append({
                    "symbol": symbol,
                    "amount": amount,
                    "entry_price": price,
                    "side": "buy"
                })
                self.portfolio["history"].append({
                    "action": "buy",
                    "symbol": symbol,
                    "amount": amount,
                    "price": price
                })
                self.save_portfolio()
                return True, "Trade executed"
            return False, "Insufficient balance"
        elif side == "sell":
            # Simplify: sell the first matching position
            for pos in self.portfolio["positions"]:
                if pos["symbol"] == symbol and pos["side"] == "buy":
                    self.portfolio["balance"] += cost
                    self.portfolio["positions"].remove(pos)
                    self.portfolio["history"].append({
                        "action": "sell",
                        "symbol": symbol,
                        "amount": amount,
                        "price": price,
                        "profit": (price - pos["entry_price"]) * amount
                    })
                    self.save_portfolio()
                    return True, "Position closed"
            return False, "No open position to sell"

    def get_status(self):
        return self.portfolio
