import os
try:
    import librosa
except ImportError:
    print("\n[ERRO FATAL] A biblioteca 'librosa' é necessária para a análise de batidas.")
    print("Abra o terminal e digite: pip install librosa\n")
    exit()
import numpy as np
from configuracoes import PASTAS, DIRETORIO_RAIZ

def analisar_bpm_e_renomear():
    print("===================================================")
    print("       ANALISADOR DE BPM DE ÁUDIO (LIBROSA)")
    print("===================================================")
    print("A analisar ficheiros nas pastas de música do projeto...\n")
    
    for pasta_relativa in PASTAS:
        if "musicas/" in pasta_relativa:
            # Puxa o caminho absoluto para as músicas criadas na raiz
            pasta_completa = os.path.join(DIRETORIO_RAIZ, pasta_relativa)
            
            if not os.path.exists(pasta_completa):
                continue
                
            for ficheiro in os.listdir(pasta_completa):
                if ficheiro.lower().endswith(('.mp3', '.wav')):
                    import re
                    # Se já foi renomeado, ignora
                    if re.search(r'(?i)\d{2,3}\s*bpm', ficheiro) or re.search(r'_\d{2,3}\.', ficheiro):
                        continue
                        
                    caminho_completo = os.path.join(pasta_completa, ficheiro)
                    print(f"A examinar: {ficheiro}...")
                    
                    try:
                        # Lê apenas o primeiro minuto para otimizar velocidade
                        y, sr = librosa.load(caminho_completo, duration=60)
                        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                        bpm = int(tempo[0]) if isinstance(tempo, (list, np.ndarray)) else int(tempo)
                        
                        nome_sem_ext, ext = os.path.splitext(ficheiro)
                        novo_nome = f"{nome_sem_ext}_{bpm}bpm{ext}"
                        novo_caminho = os.path.join(pasta_completa, novo_nome)
                        
                        os.rename(caminho_completo, novo_caminho)
                        print(f" -> Renomeado para: {novo_nome}")
                    except Exception as e:
                        print(f" -> Erro ao analisar {ficheiro}: {e}")
                        
    print("\nAnálise Total Concluída!")

if __name__ == "__main__":
    analisar_bpm_e_renomear()