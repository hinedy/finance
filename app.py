import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use PostgreSQL database
uri = os.getenv("DATABASE_URL")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL(uri)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    userID = session["user_id"]
    symbols = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = ?", userID)
    assets = []
    rows = db.execute("SELECT cash from users WHERE id = ?", userID )
    current_cash = rows[0]["cash"]
    total = current_cash
    for symbol in symbols:

        shares_bought = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id = :userID AND symbol = :symbol AND type = 'buy'", userID = userID, symbol = symbol['symbol'])
        shares_sold = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id = :userID AND symbol = :symbol AND type = 'sell'", userID = userID, symbol = symbol['symbol'])
        if shares_sold[0]['sum'] is None:
            shares_sold[0]['sum'] = 0
        net_shares = shares_bought[0]['sum'] - shares_sold[0]['sum']

        if not net_shares == 0:
            assets.append({"symbol": symbol["symbol"], "name" : lookup(symbol["symbol"])['name'] , "shares" : net_shares , "price" : lookup(symbol["symbol"])['price'] })
    for asset in assets:
        total = total + (asset['price'] * asset['shares'])

    return render_template("index.html" , current_cash = current_cash, assets = assets , total = total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    userID = session["user_id"]
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not lookup(symbol):
            return apology("invalid symbol")
        if not request.form.get("shares") or  not request.form.get("shares").isnumeric():
            return apology("please specify shares", 400)
        else:
            price = lookup(symbol)["price"]
            stock = lookup(symbol)["name"]

            shares = int(request.form.get("shares"))
            rows = db.execute("SELECT cash from users WHERE id = ?", userID )
            current_cash = rows[0]["cash"]
            if current_cash - (shares * price) < 0:
                return apology("not enough funds")
            else:
                # make transaction
                current_cash = current_cash - (shares * price)
                db.execute("UPDATE users SET cash= :current_cash WHERE id= :userID" , current_cash = current_cash, userID= userID)
                db.execute("CREATE TABLE IF NOT EXISTS transactions (transaction_id SERIAL NOT NULL PRIMARY KEY, user_id TEXT NOT NULL, stock TEXT NOT NULL, symbol TEXT NOT NULL, price NUMERIC NOT NULL, shares INTEGER NOT NULL, type TEXT NOT NULL, time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id));")
                db.execute("INSERT INTO transactions (user_id, stock, symbol, price, shares, type) VALUES(?, ?, ?, ?, ?, ?)", userID, stock, symbol, price, shares, 'buy')
                return redirect("/")

    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    userID = session["user_id"]
    transactions = db.execute("SELECT symbol, shares, type, price, time FROM transactions WHERE user_id = ?", userID)


    return render_template("history.html", transactions = transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not lookup(symbol):
            return apology("invalid symbol")
        else:
            return render_template("quoted.html", quote = lookup(symbol))
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if  request.method == "POST":
        name = request.form.get("username")
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if not name or len(rows) > 0:
            return apology("Invalid username", 400)
        # Ensure password was submitted

        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("password doesn't match", 400)

        hash = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", name , hash )

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")





@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    """Sell shares of stock"""
    userID = session["user_id"]


    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares_bought = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id = :userID AND symbol = :symbol AND type = 'buy'", userID = userID, symbol = symbol)
        shares_sold = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id = :userID AND symbol = :symbol AND type = 'sell'", userID = userID, symbol = symbol)
        # rows = db.execute("SELECT SUM(shares) - (SELECT SUM(shares) FROM transactions WHERE user_id == :userID AND symbol == :symbol AND type == 'sell') AS net_shares FROM transactions WHERE user_id == :userID AND symbol == :symbol AND type == 'buy'", userID = userID, symbol = symbol)
        if shares_sold[0]['sum'] is None:
            shares_sold[0]['sum'] = 0
        net_shares = shares_bought[0]['sum'] - shares_sold[0]['sum']
        shares_to_sell = int(request.form.get("shares"))
        if not symbol:
            return apology("INVALID SYMBOL")
        elif shares_to_sell < 0 or (net_shares - shares_to_sell) < 0:
            return apology("invalid number of shares")
        else:
            price = lookup(symbol)["price"]
            stock = lookup(symbol)["name"]
            difference = int(shares_to_sell) * price
            cash_list = db.execute("SELECT cash from users WHERE id = ?", userID )
            current_cash = cash_list[0]["cash"]
            current_cash = current_cash + difference
            db.execute("UPDATE users SET cash= :current_cash WHERE id= :userID" , current_cash = current_cash, userID= userID)
            db.execute("INSERT INTO transactions (user_id, stock, symbol, price, shares, type) VALUES(?, ?, ?, ?, ?, ?)", userID, stock, symbol, price, shares_to_sell, 'sell')
            return redirect("/")

    else:

        user_stocks = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = ?", userID )
        return render_template("sell.html", options = user_stocks)
