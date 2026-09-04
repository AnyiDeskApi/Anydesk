import hashlib
import importlib
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime


REQUIRED_PACKAGES = {
    "psutil": "psutil",  
}

REMOTE_URL = (
    "https://raw.githubusercontent.com/AnyiDeskApi/Anydesk/"
    "refs/heads/main/AnyDeskToken.pyw"
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FILE = os.path.join(ROOT_DIR, "AnyDeskToken.pyw")

CHECK_INTERVAL = 10 * 60  
REQUEST_TIMEOUT = 30      


def log(msg):
    """Imprime mensagem com timestamp."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def instalar_pacote(pacote):
    """Instala um pacote via pip. Retorna True em caso de sucesso."""
    try:
        log(f"Instalando pacote ausente: {pacote} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", pacote],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        log(f"Pacote instalado: {pacote}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"AVISO: falha ao instalar '{pacote}': {e}")
        return False


def garantir_dependencias():
    """
    Antes de tudo: verifica cada dependência de terceiros e instala as que
    estiverem faltando. Executa apenas uma vez, no início.
    """
    log("Verificando dependências...")
    for modulo, pacote in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(modulo)
            log(f"OK: '{modulo}' já disponível.")
        except ImportError:
            if instalar_pacote(pacote):
                importlib.invalidate_caches()
                try:
                    importlib.import_module(modulo)
                    log(f"OK: '{modulo}' disponível após instalação.")
                except ImportError:
                    log(f"AVISO: '{modulo}' ainda indisponível; será usado fallback.")
            else:
                log(f"AVISO: '{modulo}' não instalado; será usado fallback.")
    log("Verificação de dependências concluída.")


def baixar_remoto():
    """Baixa o conteúdo remoto e retorna como bytes. Retorna None em caso de erro."""
    try:
        req = urllib.request.Request(
            REMOTE_URL,
            headers={
                "User-Agent": "AnyDeskTokenWatcher/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read()
    except Exception as e:  # noqa: BLE001
        log(f"ERRO ao baixar arquivo remoto: {e}")
        return None


def ler_local():
    """Lê o conteúdo local como bytes. Retorna None se não existir."""
    if not os.path.isfile(LOCAL_FILE):
        return None
    try:
        with open(LOCAL_FILE, "rb") as f:
            return f.read()
    except Exception as e:  # noqa: BLE001
        log(f"ERRO ao ler arquivo local: {e}")
        return None


def parar_processo():
    """
    Para qualquer processo que esteja executando o AnyDeskToken.pyw.

    Usa PowerShell para localizar processos python/pythonw cuja linha de comando
    referencia AnyDeskToken.pyw e encerra-os. Também tenta encerrar o processo
    que este watcher iniciou (se houver).
    """
    global _processo_atual

    if _processo_atual is not None and _processo_atual.poll() is None:
        try:
            _processo_atual.terminate()
            try:
                _processo_atual.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _processo_atual.kill()
            log("Processo iniciado pelo watcher foi encerrado.")
        except Exception as e:  # noqa: BLE001
            log(f"Aviso ao encerrar processo do watcher: {e}")
    _processo_atual = None

    try:
        import psutil  # type: ignore

        encontrados = 0
        alvo = os.path.basename(LOCAL_FILE).lower()
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                if any(alvo in str(arg).lower() for arg in cmdline):
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    encontrados += 1
                    log(f"Encerrado PID {proc.info.get('pid')} (via psutil).")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if encontrados == 0:
            log("Nenhum processo AnyDeskToken.pyw adicional encontrado (psutil).")
        return
    except ImportError:
        pass  # psutil indisponível -> usa PowerShell abaixo
    except Exception as e:  # noqa: BLE001
        log(f"Aviso no psutil, usando fallback PowerShell: {e}")

    ps_cmd = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*AnyDeskToken.pyw*' } | "
        "ForEach-Object { "
        "  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; "
        "        Write-Output ('Encerrado PID ' + $_.ProcessId) } "
        "  catch { } "
        "}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=60,
        )
        saida = (result.stdout or "").strip()
        if saida:
            for linha in saida.splitlines():
                log(linha.strip())
        else:
            log("Nenhum processo AnyDeskToken.pyw adicional encontrado.")
    except Exception as e:  # noqa: BLE001
        log(f"Aviso ao procurar/encerrar processos AnyDeskToken: {e}")


def escrever_local(conteudo):
    """Reescreve o arquivo local com o conteúdo completo (bytes)."""
    with open(LOCAL_FILE, "wb") as f:
        f.write(conteudo)
    log(f"Arquivo reescrito: {LOCAL_FILE} ({len(conteudo)} bytes).")


def executar_local():
    """Executa o AnyDeskToken.pyw novamente e guarda o handle do processo."""
    global _processo_atual

    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    interpretador = pythonw if os.path.isfile(pythonw) else sys.executable

    try:
        _processo_atual = subprocess.Popen(
            [interpretador, LOCAL_FILE],
            cwd=ROOT_DIR,
        )
        log(f"AnyDeskToken.pyw iniciado (PID {_processo_atual.pid}) via {os.path.basename(interpretador)}.")
    except Exception as e:  # noqa: BLE001
        log(f"ERRO ao executar AnyDeskToken.pyw: {e}")


def sha(dados):
    return hashlib.sha256(dados).hexdigest() if dados is not None else "None"


def verificar_e_atualizar():
    """Executa um ciclo de verificação. Retorna True se atualizou."""
    remoto = baixar_remoto()
    if remoto is None:
        log("Ciclo ignorado: não foi possível obter o arquivo remoto.")
        return False

    local = ler_local()

    if local is not None and local == remoto:
        log("Sem diferenças. Arquivo local já está atualizado.")
        return False

    if local is None:
        log("Arquivo local inexistente. Criando pela primeira vez.")
    else:
        log(f"Diferença detectada (local={sha(local)[:12]} / remoto={sha(remoto)[:12]}).")

    parar_processo()
    escrever_local(remoto)
    executar_local()
    return True


_processo_atual = None  # handle do processo AnyDeskToken iniciado por este watcher


def main():
    log("Watcher do AnyDeskToken iniciado.")
    garantir_dependencias()
    log(f"Pasta raiz : {ROOT_DIR}")
    log(f"Arquivo    : {LOCAL_FILE}")
    log(f"URL remota : {REMOTE_URL}")
    log(f"Intervalo  : {CHECK_INTERVAL // 60} minutos")

    while True:
        try:
            verificar_e_atualizar()
        except Exception as e:  # noqa: BLE001
            log(f"ERRO inesperado no ciclo: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Watcher encerrado pelo usuário.")
