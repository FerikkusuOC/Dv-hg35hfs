import os
import cv2
import sys
import gc
import urllib.request
import threading
from configuracoes import DEBUG_MODE, RESOLUCAO

# Variáveis globais para manter o modelo carregado na GPU e economizar tempo
_restaurador = None
_modelo_lock = threading.Lock()

def baixar_modelo_se_necessario(url, caminho):
    if not os.path.exists(caminho):
        print(f"  [STATUS] Baixando modelo ultra-rápido de Anime (~17MB)...")
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        urllib.request.urlretrieve(url, caminho)

def _carregar_modelo():
    """
    Função interna que carrega o modelo RealESRGAN na VRAM apenas na primeira vez 
    que for necessário, deixando-o engatilhado para os próximos cliques no site.
    """
    global _restaurador
    
    with _modelo_lock:
        if _restaurador is not None:
            return True # Já está carregado

        try:
            import torchvision.transforms.functional as F
            sys.modules['torchvision.transforms.functional_tensor'] = F
            
            from basicsr.archs.srvgg_arch import SRVGGNetCompact
            from realesrgan import RealESRGANer
        except Exception as e:
            print(f"  [ERRO IA] Falha interna ao carregar as bibliotecas do RealESRGAN: {e}")
            return False

        url_modelo = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth'
        caminho_modelo = os.path.join('weights', 'realesr-animevideov3.pth')
        baixar_modelo_se_necessario(url_modelo, caminho_modelo)
        
        try:
            if DEBUG_MODE: print("  [DEBUG IA] Alocando AnimeVideoV3 na GPU...")
            modelo_base = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=16, upscale=4, act_type='prelu')
            
            _restaurador = RealESRGANer(
                scale=4,
                model_path=caminho_modelo,
                model=modelo_base,
                tile=0, # Usa a VRAM toda para ser instantâneo
                half=True
            )
            return True
        except Exception as e:
            print(f"  [ERRO FATAL IA] Falha ao carregar os pesos na GPU: {e}")
            return False

def aprimorar_imagem(caminho_in, caminho_out):
    """
    A ponte que o servidor Web chama. Recebe a foto, passa pela IA e devolve limpa.
    """
    if not os.path.exists(caminho_in):
        return False
        
    sucesso_carregamento = _carregar_modelo()
    if not sucesso_carregamento or _restaurador is None:
        # Se a IA quebrou, apenas copia a imagem original para não travar o fluxo do site
        import shutil
        shutil.copy(caminho_in, caminho_out)
        return False

    try:
        img = cv2.imread(caminho_in, cv2.IMREAD_COLOR)
        if img is None:
            return False

        # Otimização original mantida: Reduz imagens gigantes antes da IA
        limite_resolucao = max(RESOLUCAO[0], RESOLUCAO[1])
        h, w = img.shape[:2]
        max_dim = max(h, w)
        if max_dim > limite_resolucao:
            fator = limite_resolucao / max_dim
            img = cv2.resize(img, (int(w * fator), int(h * fator)), interpolation=cv2.INTER_AREA)

        # O Mágico em ação:
        with _modelo_lock:
            img_limpa, _ = _restaurador.enhance(img, outscale=1)
            
        cv2.imwrite(caminho_out, img_limpa)
        return True

    except Exception as e:
        print(f"  [ERRO IA] Falha ao processar {caminho_in}: {e}")
        import shutil
        shutil.copy(caminho_in, caminho_out)
        return False

def liberar_memoria():
    """
    (Opcional) Pode ser chamada pelo servidor web ao finalizar o projeto 
    para devolver a VRAM da placa de vídeo para o Windows.
    """
    global _restaurador
    with _modelo_lock:
        if _restaurador is not None:
            del _restaurador
            _restaurador = None
            try:
                import torch
                if torch.cuda.is_available(): torch.cuda.empty_cache()
            except: pass
            gc.collect()