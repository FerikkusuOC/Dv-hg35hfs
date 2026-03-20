import time
import urllib.parse
import threading
import os
import asyncio
import aiohttp
import requests
import base64
import urllib3
import json
from io import BytesIO
from PIL import Image
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from duckduckgo_search import DDGS

from configuracoes import *

# Suprime avisos de conexões não seguras ao forçar downloads
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

lock_chaves = threading.Lock()
lock_chromium = threading.Lock()
lock_ddg = threading.Lock() # O pedágio anti-ban do motor gratuito

# --- DICIONÁRIO GLOBAL DE CHAVES QUEIMADAS ---
CHAVES_ESGOTADAS = {'apify': set(), 'serper': set()}

def simplificar_query(texto):
    palavras = texto.split()
    if len(palavras) > 3:
        return " ".join(palavras[:2]) + " anime"
    return texto

def buscar_serper(termo, chave):
    url = "https://google.serper.dev/images"
    headers = {'X-API-KEY': chave, 'Content-Type': 'application/json'}
    # num: 50 (Tiro de espingarda para garantir 5 links válidos rapidamente) | tbs: isz:l (HD)
    payload = json.dumps({"q": termo, "num": 50, "tbs": "isz:l"})
    try:
        res = requests.post(url, headers=headers, data=payload, timeout=15)
        if res.status_code == 200:
            return [img['imageUrl'] for img in res.json().get('images', [])]
        if res.status_code in [401, 403]: return "ESGOTADO"
    except: pass
    return None

def buscar_apify(termo, chave):
    url = f"https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items?token={chave}"
    # Pedimos 50 resultados aqui também
    payload = {"searchType": "image", "queries": termo + " high resolution", "maxPagesPerQuery": 1, "resultsPerPage": 50}
    try:
        res = requests.post(url, json=payload, timeout=25)
        if res.status_code in [200, 201]:
            dados = res.json()
            return [img['imageUrl'] for img in dados if 'imageUrl' in img]
        if res.status_code in [401, 402, 403]: return "ESGOTADO"
    except: pass
    return None

def buscar_nativo(termo):
    # Fila indiana para não tomar bloqueio de IP do DuckDuckGo
    with lock_ddg:
        time.sleep(1.0)
        try:
            resultados = DDGS().images(termo, max_results=50, size="Large")
            return [img['image'] for img in resultados]
        except: pass
        return None

def pre_buscar_urls(texto_busca, indice_cena):
    termo_original = texto_busca.split(',')[0].strip()
    termos_tentativa = [termo_original, simplificar_query(termo_original)]
    
    total_serper = len(SERPER_KEYS)
    total_apify = len(APIFY_KEYS)

    for termo in termos_tentativa:
        if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: Iniciando busca para '{termo}'...")
        
        # 1. SERPER (O Rei da Velocidade voltou ao topo)
        if SERPER_KEYS:
            for idx, chave in enumerate(SERPER_KEYS, 1):
                if chave in CHAVES_ESGOTADAS['serper'] or not chave: continue
                if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: ↳ [Motor 1] Acionando SERPER (Chave {idx}/{total_serper})...")
                
                resultado = buscar_serper(termo, chave)
                if resultado == "ESGOTADO":
                    CHAVES_ESGOTADAS['serper'].add(chave)
                    continue
                if resultado and len(resultado) > 0:
                    if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: ✅ SERPER encontrou {len(resultado)} links HD!")
                    return (resultado, f"SERPER ({idx}/{total_serper})")

        # 2. APIFY (Backup Robusto em Nuvem)
        if APIFY_KEYS:
            for idx, chave in enumerate(APIFY_KEYS, 1):
                if chave in CHAVES_ESGOTADAS['apify'] or not chave: continue
                if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: ↳ [Motor 2] Acionando APIFY (Chave {idx}/{total_apify})...")
                
                resultado = buscar_apify(termo, chave)
                if resultado == "ESGOTADO":
                    CHAVES_ESGOTADAS['apify'].add(chave)
                    continue
                if resultado and len(resultado) > 0:
                    if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: ✅ APIFY encontrou {len(resultado)} links HD!")
                    return (resultado, f"APIFY ({idx}/{total_apify})")

        # 3. DUCKDUCKGO (Segurança Nativa)
        if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: ↳ [Motor 3] Acionando DUCKDUCKGO Nativo...")
        resultado = buscar_nativo(termo)
        if resultado and len(resultado) > 0:
            if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: ✅ DUCKDUCKGO encontrou {len(resultado)} links HD!")
            return (resultado, "DUCKDUCKGO")

        if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: Termo '{termo}' esgotou todas as APIs. Simplificando...")

    return ([], "NENHUM")

async def worker_download(session, url, indice_cena, imagens_salvas, lock_salvamento):
    if len(imagens_salvas) >= 5: return 'ignorado'
    
    if url.startswith('data:image'):
        try:
            img_data = base64.b64decode(url.split(',', 1)[1])
            Image.open(BytesIO(img_data)).verify()
            with lock_salvamento:
                if len(imagens_salvas) < 5:
                    caminho = f"temp_imagens/cena_{indice_cena:03d}_cand_{len(imagens_salvas)+1}.jpg"
                    with open(caminho, 'wb') as f: f.write(img_data)
                    imagens_salvas.append(caminho)
            return 'ok'
        except: return 'erro'

    img_data = None
    headers_blindados = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
    }

    try:
        async with session.get(url, headers=headers_blindados, timeout=10) as resp:
            if resp.status == 200: img_data = await resp.read()
    except: pass

    if not img_data:
        try:
            res = requests.get(url, headers=headers_blindados, timeout=10, verify=False)
            if res.status_code == 200: img_data = res.content
        except: pass

    if img_data:
        try:
            Image.open(BytesIO(img_data)).verify()
            with lock_salvamento:
                if len(imagens_salvas) < 5:
                    caminho = f"temp_imagens/cena_{indice_cena:03d}_cand_{len(imagens_salvas)+1}.jpg"
                    with open(caminho, 'wb') as f: f.write(img_data)
                    imagens_salvas.append(caminho)
                    if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: +1 Imagem salva! ({len(imagens_salvas)}/5)")
            return 'ok'
        except: return 'corrompido'
        
    return 'erro'

async def orquestrar_downloads_async(urls, indice_cena, imagens_salvas, lock_salvamento):
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tarefas = [worker_download(session, url, indice_cena, imagens_salvas, lock_salvamento) for url in urls]
        for tarefa in asyncio.as_completed(tarefas):
            await tarefa
            if len(imagens_salvas) >= 5: break

def baixar_candidatos(texto_busca, indice_cena, urls_pre_carregadas=None):
    imagens_salvas = []
    termo = texto_busca.split(',')[0].strip()
    urls_ja_tentadas = set()
    lock_salvamento = threading.Lock()
    
    try:
        if urls_pre_carregadas and isinstance(urls_pre_carregadas, tuple):
            urls_agora, motor_usado = urls_pre_carregadas
        else:
            urls_agora, motor_usado = pre_buscar_urls(texto_busca, indice_cena)
        
        if urls_agora:
            if DEBUG_MODE: print(f"\n      [STATUS] Cena {indice_cena:03d}: Extraindo 5 imagens do banco [{motor_usado}]...")
            asyncio.run(orquestrar_downloads_async(urls_agora, indice_cena, imagens_salvas, lock_salvamento))

        if len(imagens_salvas) < 5:
            driver = None
            with lock_chromium: 
                if DEBUG_MODE: print(f"      [DEBUG] Cena {indice_cena:03d}: Imagens insuficientes. Acionando Chrome (Plano Z)...")
                try:
                    options = uc.ChromeOptions()
                    options.add_argument('--headless=new')
                    options.add_argument('--window-size=1920,1080') 
                    options.add_argument('--disable-gpu')
                    options.add_argument('--no-sandbox')
                    driver = uc.Chrome(options=options)
                    driver.set_page_load_timeout(15)

                    termo_certo = simplificar_query(termo)
                    url_busca = f"https://www.google.com/search?q={urllib.parse.quote(termo_certo)}&tbm=isch&tbs=isz:l"
                    
                    driver.get(url_busca)
                    WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "img.rg_i, img.YQ4gaf")))
                    
                    for i in range(50): 
                        if len(imagens_salvas) >= 5: break
                        img_clicavel = driver.execute_script("var imgs = document.querySelectorAll('img.rg_i'); return imgs[arguments[0]];", i)
                        if not img_clicavel: break 
                        driver.execute_script("arguments[0].click();", img_clicavel)
                        time.sleep(0.5)
                        
                        painel_imgs = driver.find_elements(By.XPATH, "//img[starts-with(@src, 'http')]")
                        for img in painel_imgs:
                            src = img.get_attribute("src")
                            if src and "encrypted-tbn0" not in src and "gstatic.com" not in src:
                                if src not in urls_ja_tentadas: 
                                    urls_ja_tentadas.add(src)
                                    try:
                                        res = requests.get(src, headers={'User-Agent': 'Mozilla/5.0'}, timeout=(2, 5), verify=False)
                                        if res.status_code == 200:
                                            Image.open(BytesIO(res.content)).verify()
                                            caminho = f"temp_imagens/cena_{indice_cena:03d}_cand_{len(imagens_salvas)+1}.jpg"
                                            with open(caminho, 'wb') as f: f.write(res.content)
                                            imagens_salvas.append(caminho)
                                    except: pass
                                    break 
                except: pass
                finally:
                    if driver:
                        try: driver.quit()
                        except: pass

        while len(imagens_salvas) < 5:
            caminho = f"temp_imagens/cena_{indice_cena:03d}_cand_{len(imagens_salvas)+1}.jpg"
            Image.new('RGB', (1280, 720), color='#1a1a1a').save(caminho)
            imagens_salvas.append(caminho)
            
    except Exception as e:
        if DEBUG_MODE: print(f"      [ERRO CRÍTICO] Falha cena {indice_cena:03d}: {e}")
    finally:
        with open(f"temp_imagens/cena_{indice_cena:03d}_ok.flag", 'w') as f:
            f.write('ok')
            
    return True