from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
import time
from urllib.parse import unquote

# Importação correta
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("ERRO CRÍTICO: A biblioteca 'exnovaapi' não foi encontrada.")
    print("Execute 'pip install git+https://github.com/CassDs/exnovaapi.git' no seu terminal.")
    exit()

# ==============================================================================
#  CONFIGURAÇÃO DO FILTRO DE ATIVOS (REATIVADO)
# ==============================================================================

# O robô agora voltará a usar a lista restrita de ativos abaixo.
ATIVOS_PERMITIDOS = [
    # Pares de Moedas (Forex)
    # --- Mercado Aberto (Semana) ---
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
    "CADCHF", "CADJPY", "CHFJPY", "EURAUD", "EURCAD",
    "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
    "GBPUSD", "NZDCAD", "NZDJPY", "USDBRL", "USDCAD",
    "USDCHF",
    # --- Mercado OTC (Fim de Semana) ---
    "AUDCAD-OTC", "AUDCHF-OTC", "AUDJPY-OTC", "AUDNZD-OTC", "AUDUSD-OTC",
    "CADCHF-OTC", "CADJPY-OTC", "CHFJPY-OTC", "EURAUD-OTC", "EURCAD-OTC",
    "EURCHF-OTC", "EURGBP-OTC", "EURJPY-OTC", "EURNZD-OTC", "EURUSD-OTC",
    "GBPAUD-OTC", "GBPCAD-OTC", "GBPCHF-OTC", "GBPJPY-OTC", "GBPNZD-OTC",
    "GBPUSD-OTC", "NZDCAD-OTC", "NZDJPY-OTC", "USDBRL-OTC", "USDCAD-OTC",
    "USDCHF-OTC",

    # Criptomoedas
    # --- Mercado Aberto (Semana) ---
    "BTCUSD", "DOGEUSD-L", "TRXUSD",
    # --- Mercado OTC (Fim de Semana) ---
    "BTCUSD-OTC-op", "TRXUSD-L",

    # Commodities
    # --- Mercado Aberto (Semana) ---
    "XAUUSD", # Ouro
    # --- Mercado OTC (Fim de Semana) ---
    "XAUUSD-OTC",

    # Ações de Empresas
    # --- Mercado Aberto (Semana) ---
    "AMAZON", "APPLE", "COKE", "GOOGLE", "FACEBOOK",
    "MCDON", "NIKE", "SNAP", "TESLA",
    # --- Mercado OTC (Fim de Semana) ---
    "AMAZON-OTC", "APPLE-OTC", "COKE-OTC", "GOOGLE-OTC", "FB-OTC",
    "MCDON-OTC", "NIKE-OTC", "SNAP-OTC", "TESLA-OTC",
]
# ==============================================================================


# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Inicializa o Flask
app = Flask(__name__)
CORS(app)

api_connection = None

@app.route('/api/connect', methods=['POST'])
def connect_to_exnova():
    global api_connection
    data = request.get_json()
    email, password = data.get('email'), data.get('senha')
    account_type = data.get('account_type', 'PRACTICE').upper()

    if not email or not password:
        return jsonify({"error": "Email e senha são obrigatórios"}), 400

    logging.info(f"Tentando conectar com o email: {email} na conta {account_type}")
    api_connection = Exnova(email, password)
    status, reason = api_connection.connect()

    if status:
        logging.info("Conexão com a Exnova bem-sucedida!")
        api_connection.change_balance(account_type)
        balance = api_connection.get_balance()
        return jsonify({
            "message": "Conectado com sucesso!",
            "balance": balance,
            "currency": api_connection.get_currency()
        })
    else:
        api_connection = None
        logging.error(f"Falha na conexão: {reason}")
        return jsonify({"error": f"Credenciais inválidas ou erro na conexão: {reason}"}), 401


@app.route('/api/open-pairs', methods=['GET'])
def get_open_pairs():
    if not api_connection or not api_connection.check_connect():
        return jsonify({"error": "Não autenticado."}), 401

    logging.info("Buscando e filtrando os ativos permitidos...")

    try:
        all_assets = api_connection.get_all_init_v2()
        open_pairs = []

        for asset_type in ['binary', 'turbo', 'digital-option']:
            if asset_type in all_assets and 'actives' in all_assets[asset_type]:
                for asset_data in all_assets[asset_type]['actives'].values():
                    if isinstance(asset_data, dict) and asset_data.get('enabled') and not asset_data.get('is_suspended'):
                        name = asset_data.get('name', '').replace('front.', '')

                        # O FILTRO FOI REATIVADO.
                        if name not in ATIVOS_PERMITIDOS:
                            continue

                        payout = 100 - asset_data.get('option', {}).get('profit', {}).get('commission', 100)
                        open_pairs.append({
                            "name": name,
                            "payout": int(payout)
                        })

        final_pairs = {}
        for pair in open_pairs:
            if pair['name'] not in final_pairs or pair['payout'] > final_pairs[pair['name']]['payout']:
                final_pairs[pair['name']] = pair

        logging.info(f"Encontrados {len(final_pairs)} ativos permitidos e abertos.")
        return jsonify(list(final_pairs.values()))

    except Exception as e:
        logging.error(f"Erro ao buscar ativos: {e}")
        return jsonify({"error": "Falha ao buscar os ativos."}), 500


@app.route('/api/candles/<string:pair>/<int:timeframe>', methods=['GET'])
def get_candles(pair, timeframe):
    if not api_connection or not api_connection.check_connect():
        return jsonify({"error": "Não autenticado."}), 401

    decoded_pair = unquote(pair)
    timeframe_in_seconds = timeframe * 60
    candles = api_connection.get_candles(decoded_pair, timeframe_in_seconds, 300, time.time())

    if candles:
        return jsonify(candles)
    else:
        logging.warning(f"Não foi possível buscar velas para o par: {decoded_pair}")
        return jsonify({"error": f"Não foi possível buscar as velas para o par {decoded_pair}"}), 404


if __name__ == '__main__':
    print("="*50)
    print("Servidor do Robô Prisma IA iniciado.")
    print("NÃO FECHE ESTE TERMINAL!")
    print("Agora, abra o arquivo 'robo-sinais.html' no seu navegador.")
    print("="*50)
    app.run(host='127.0.0.1', port=5000)