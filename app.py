
from flask import Flask, request, render_template_string
import requests
import numpy as np

API_KEY = "UiTsFvZKsvF84PPu4wT6LGsfOlcO6XO6"
BASE_URL = "https://financialmodelingprep.com/api/v3"

app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Valoración con FMP</title></head>
<body>
    <h2>Ingresa Tickers Separados por Coma</h2>
    <form method="POST">
        <input type="text" name="tickers" style="width:400px;" placeholder="Ej: AAPL, MSFT"/>
        <input type="submit" value="Analizar"/>
    </form>
    {% if resultados %}
        <h3>Resultados:</h3>
        {% for r in resultados %}
            <h4>{{ r['Ticker'] }}</h4>
            {% if r.get('Error') %}
                <p style="color:red;">Error: {{ r['Error'] }}</p>
            {% else %}
                <ul>
                    <li>Valor Intrínseco Estimado: {{ r['Valor Intrínseco Estimado por Acción'] }}</li>
                    <li>Precio Actual: {{ r['Precio Actual'] }}</li>
                    <li>¿Infravalorado?: {{ r['Infravalorado'] }}</li>
                    <li>Ohlson Score: {{ r['Ohlson Score'] }}</li>
                    <li>Probabilidad Alta de Quiebra: {{ r['Probabilidad Alta de Quiebra'] }}</li>
                </ul>
            {% endif %}
        {% endfor %}
    {% endif %}
</body>
</html>
'''

def fetch_json(endpoint):
    url = f"{BASE_URL}/{endpoint}&apikey={API_KEY}"
    r = requests.get(url)
    return r.json() if r.status_code == 200 else None

def analizar_ticker(ticker):
    try:
        inc = fetch_json(f"income-statement/{ticker}?limit=2")
        bal = fetch_json(f"balance-sheet-statement/{ticker}?limit=2")
        cf = fetch_json(f"cash-flow-statement/{ticker}?limit=2")
        quote = fetch_json(f"quote/{ticker}?")

        if not inc or not bal or not cf or not quote:
            return {'Ticker': ticker, 'Error': 'Datos insuficientes'}

        income = inc[0]
        balance = bal[0]
        cashflow = cf[0]
        market_price = quote[0].get("price", 1)
        shares = quote[0].get("sharesOutstanding", 10000000)

        EBIT = income.get("ebit", 0)
        Taxes = income.get("incomeTaxExpense", EBIT * 0.25)
        T = Taxes / EBIT if EBIT else 0.25
        NOPAT = EBIT * (1 - T)
        Dep = cashflow.get("depreciationAndAmortization", 0)
        CapEx = -cashflow.get("capitalExpenditure", 0)
        delta_NOF = balance.get("totalCurrentAssets", 0) - balance.get("totalCurrentLiabilities", 0)
        CFO = cashflow.get("operatingCashFlow", 0)
        Interest = income.get("interestExpense", 0)
        delta_Debt = cashflow.get("netDebtRepayment", 0)

        FCFF = NOPAT + Dep - CapEx - delta_NOF
        FCFE = FCFF - Interest * (1 - T) + delta_Debt

        g = 0.03
        wacc = 0.10
        tv = FCFF * (1 + g) / (wacc - g)
        pv_tv = tv / ((1 + wacc) ** 3)
        pv_fcf = sum([FCFF / ((1 + wacc) ** i) for i in range(1, 4)])
        enterprise_value = pv_fcf + pv_tv
        valor_intrinseco = enterprise_value / shares

        TLTA = balance.get("totalLiabilities", 1) / balance.get("totalAssets", 1)
        WCTA = (balance.get("totalCurrentAssets", 0) - balance.get("totalCurrentLiabilities", 0)) / balance.get("totalAssets", 1)
        CLCA = balance.get("totalCurrentLiabilities", 1) / balance.get("totalCurrentAssets", 1)
        OENEG = 1 if balance.get("totalStockholdersEquity", 1) < 0 else 0
        NITA = income.get("netIncome", 0) / balance.get("totalAssets", 1)
        FUTL = CFO / balance.get("totalLiabilities", 1)
        INTWO = 1 if income.get("netIncome", 0) < 0 else 0
        prev_revenue = inc[1].get("revenue", 1)
        CHIN = (income.get("revenue", 0) - prev_revenue) / abs(prev_revenue) if prev_revenue != 0 else 0

        O_score = (
            -1.32 - 0.407 * np.log(balance.get("totalAssets", 1)) +
            6.03 * TLTA - 1.43 * WCTA + 0.076 * CLCA - 1.72 * OENEG -
            2.37 * NITA - 1.83 * FUTL + 0.285 * INTWO - 0.521 * CHIN
        )

        return {
            'Ticker': ticker,
            'Valor Intrínseco Estimado por Acción': round(valor_intrinseco, 2),
            'Precio Actual': round(market_price, 2),
            'Infravalorado': valor_intrinseco > market_price,
            'Ohlson Score': round(O_score, 2),
            'Probabilidad Alta de Quiebra': O_score > 0.5
        }

    except Exception as e:
        return {'Ticker': ticker, 'Error': str(e)}

@app.route("/", methods=["GET", "POST"])
def home():
    resultados = []
    if request.method == "POST":
        tickers = request.form['tickers'].upper().replace(" ", "").split(",")
        for t in tickers:
            resultados.append(analizar_ticker(t))
    return render_template_string(HTML_TEMPLATE, resultados=resultados)

if __name__ == "__main__":
    app.run()
