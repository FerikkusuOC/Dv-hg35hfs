import sys
import os
import json
import re
import base64
import warnings
import subprocess
from io import BytesIO
import requests
from PIL import Image
import undetected_chromedriver as uc
import time
import platform

# --- DETECÇÃO GLOBAL DE SISTEMA ---
SISTEMA = platform.system()

try:
    import psutil
except ImportError:
    print("\n[ERRO FATAL] A biblioteca 'psutil' é necessária para o dimensionamento de hardware.")
    print("Abra o terminal e digite: pip install psutil\n")
    sys.exit()

# ==========================================
# PATCH DE CORREÇÃO DO CHROMIUM (WINERROR 6)
# ==========================================
_original_quit = uc.Chrome.quit
def _patched_quit(self):
    try:
        _original_quit(self)
    except OSError:
        pass
uc.Chrome.quit = _patched_quit

warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*socket")

# ==========================================
# MODO DEBUG E CONFIGURAÇÕES GLOBAIS
# ==========================================
DEBUG_MODE = '--debug' in sys.argv
if DEBUG_MODE:
    print("=========================================")
    print(f" 🛠️  MODO DEBUG ATIVADO ({SISTEMA})")
    print("=========================================")

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

TIPO_DE_VIDEO = '16:9'
RESOLUCAO = (1920, 1080) if TIPO_DE_VIDEO == '16:9' else (1080, 1920)

# ==========================================
# GERENCIAMENTO INTELIGENTE DE PASTAS (BLINDADO COLAB/LINUX)
# ==========================================
# Em notebooks (Colab), __file__ pode não existir no escopo global.
if '__file__' in globals():
    DIRETORIO_PYTHON = os.path.dirname(os.path.abspath(__file__))
    DIRETORIO_RAIZ = os.path.dirname(DIRETORIO_PYTHON)
else:
    DIRETORIO_PYTHON = os.getcwd()
    DIRETORIO_RAIZ = os.getcwd()

# Se rodar direto no /content do Colab, a raiz e o python dir podem ser os mesmos
if not os.path.exists(os.path.join(DIRETORIO_RAIZ, 'api_keys.json')) and os.path.exists(os.path.join(DIRETORIO_PYTHON, 'api_keys.json')):
    DIRETORIO_RAIZ = DIRETORIO_PYTHON

PASTA_ENTRADA = os.path.join(DIRETORIO_RAIZ, "Entrada")
PASTA_SAIDA = os.path.join(DIRETORIO_RAIZ, "Saída")

os.makedirs(PASTA_ENTRADA, exist_ok=True)
os.makedirs(PASTA_SAIDA, exist_ok=True)

arquivos_suportados = [f for f in os.listdir(PASTA_ENTRADA) if f.lower().endswith(('.mp3', '.wav'))]
ARQUIVO_AUDIO = os.path.join(PASTA_ENTRADA, arquivos_suportados[0]) if arquivos_suportados else None
    
PASTAS = [
    'temp_imagens', 'imagens_finais', 'imagens_finais/upscale', 
    'musicas/Raiva', 'musicas/Animado', 'musicas/Calmo', 
    'musicas/Sombrio', 'musicas/Dramático', 'musicas/Vibrante', 
    'musicas/Alegre', 'musicas/Inspirador', 'musicas/Romântico', 
    'musicas/Melancólico'
]

# Cria as pastas a partir do diretório de onde o script foi chamado
for pasta in PASTAS:
    os.makedirs(os.path.join(DIRETORIO_RAIZ, pasta), exist_ok=True)

# ==========================================
# CARREGAMENTO BLINDADO DE CHAVES (api_keys.json)
# ==========================================
API_KEYS = []
GROQ_KEY = ""
APIFY_KEYS = []
SERPER_KEYS = []

try:
    caminho_keys = os.path.join(DIRETORIO_RAIZ, 'api_keys.json')
    with open(caminho_keys, 'r', encoding='utf-8') as f:
        dados = json.load(f)
        
        API_KEYS = dados.get('gemini_keys', [])
        GROQ_KEY = dados.get('groq_api_key', "")
        APIFY_KEYS = dados.get("apify_keys", [])
        
        chaves_serper_raw = dados.get('serper_api_key', [])
        if isinstance(chaves_serper_raw, str):
            SERPER_KEYS = [chaves_serper_raw] if chaves_serper_raw else []
        else:
            SERPER_KEYS = chaves_serper_raw
            
except FileNotFoundError:
    print(f"\n[ERRO] Arquivo 'api_keys.json' não encontrado em: {DIRETORIO_RAIZ}")
    print("Se estiver no Colab, certifique-se de fazer o upload do arquivo para a raiz do projeto.")
    sys.exit()
except json.JSONDecodeError:
    print("\n[ERRO] Arquivo 'api_keys.json' está com o formato JSON inválido.")
    sys.exit()

# ==========================================
# VARIÁVEIS DE ESTADO E HIERARQUIA DE MODELOS
# ==========================================
GEMINI_REVISOR_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-pro",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite"
]
WHISPER_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]

FALLBACK_TEXTO = [
    ("groq", "llama-3.3-70b-versatile"),
    ("groq", "qwen-2.5-32b")
]

ESTADO_REVISOR = {
    'gemini_esgotado': False,
    'gemini_permanentes': set(),
    'gemini_cooldowns': {},
    'fallback_idx': 0
}

ESTADO_VISAO = {}

# ==========================================
# FUNÇÕES DE HARDWARE E UTILITÁRIOS GERAIS
# ==========================================
def obter_recursos_sistema():
    ram_disponivel = psutil.virtual_memory().available / (1024**3)
    vram_disponivel = 0.0
    try:
        # Tenta checar a GPU (funciona no Windows e na T4 do Linux/Colab)
        result = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], encoding='utf-8')
        vrams = [float(x.strip()) for x in result.strip().split('\n')]
        vram_disponivel = max(vrams) / 1024.0
    except Exception:
        if DEBUG_MODE: print("      [Aviso] Placa NVIDIA não detectada ou ocupada. Operando em modo de segurança.")
    return vram_disponivel, ram_disponivel

def escolher_modelo_whisper(vram, ram):
    if vram >= 10.0 and ram >= 16.0: return "large-v3"
    if vram >= 6.0 and ram >= 10.0: return "large-v3-turbo"
    if vram >= 5.0 and ram >= 8.0: return "medium"
    if vram >= 2.0 and ram >= 4.0: return "small"
    if vram >= 1.0 and ram >= 3.0: return "base"
    return "tiny"

def escolher_modelo_junior(vram, ram):
    if vram >= 4.8 and ram >= 7.0: return "qwen3:8b-q4_K_M"
    if vram >= 3.0 and ram >= 8.0: return "qwen2.5:3b"
    return "qwen3:4b-q4_K_M"

def escolher_modelo_senior(vram, ram):
    if vram >= 43.0 and ram >= 50.0: return "qwen:72b-text-q4_K_M"
    if vram >= 19.5 and ram >= 24.0: return "qwen3:32b-q4_K_M"
    if vram >= 8.5 and ram >= 12.0: return "qwen3:14b-q4_K_M"
    if vram >= 4.8 and ram >= 7.0: return "qwen3:8b-q4_K_M"
    if vram >= 3.0 and ram >= 8.0: return "qwen2.5:3b"
    return "qwen3:4b-q4_K_M"

def descarregar_modelo_ollama(nome_modelo):
    if DEBUG_MODE: print(f"      [DEBUG] Descarregando modelo '{nome_modelo}' da VRAM/RAM...")
    try: requests.post("http://127.0.0.1:11434/api/chat", json={"model": nome_modelo, "keep_alive": 0}, timeout=5)
    except: pass

def extrair_json_seguro(texto_ia):
    match_list = re.search(r'\[\s*\{.*?\}\s*\]', texto_ia, re.DOTALL)
    if match_list:
        try: return json.loads(match_list.group(0))
        except: pass
        
    match_dict = re.search(r'\{\s*"id_inicio".*?\}', texto_ia, re.DOTALL)
    if match_dict:
        try: return [json.loads(match_dict.group(0))] 
        except: pass
    return None

def codificar_imagem_base64_comprimida(caminho_imagem):
    img = Image.open(caminho_imagem)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.thumbnail((600, 600)) 
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=70) 
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def marcar_chave_serper_expirada(chave_esgotada):
    try:
        caminho_keys = os.path.join(DIRETORIO_RAIZ, 'api_keys.json')
        with open(caminho_keys, "r", encoding="utf-8") as f:
            conteudo = f.read()
        novo_conteudo = conteudo.replace(f'"{chave_esgotada}"', f'"{chave_esgotada} // EXPIRADA, SUBSTITUA"')
        with open(caminho_keys, "w", encoding="utf-8") as f:
            f.write(novo_conteudo)
    except Exception as e:
        if DEBUG_MODE: print(f"      [ERRO] Não foi possível atualizar o api_keys.json: {e}")

def medir_velocidade_internet():
    if DEBUG_MODE: print("      [DEBUG] [Rede] Medindo a velocidade da internet...")
    url = "https://speed.cloudflare.com/__down?bytes=1048576" 
    try:
        start_time = time.time()
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            tamanho_mb = len(res.content) / (1024 * 1024)
            velocidade = tamanho_mb / (time.time() - start_time)
            if DEBUG_MODE: print(f"      [DEBUG] [Rede] Velocidade detectada: {velocidade:.2f} MB/s")
            return velocidade
    except: pass
    return 10.0 

def calcular_workers_cenas(velocidade_mbps):
    if velocidade_mbps >= 30.0: return 6  
    if velocidade_mbps >= 15.0: return 4  
    if velocidade_mbps >= 5.0:  return 2  
    return 1