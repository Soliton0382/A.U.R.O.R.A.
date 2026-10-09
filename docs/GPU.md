# Aurora con una GPU NVIDIA: driver, CUDA, ragionatore locale

Con una GPU NVIDIA abbastanza grande Aurora ragiona **in locale**: niente esce dal computer, niente provider, niente
costi a token. Senza GPU (o con una troppo piccola) funziona lo stesso con un ragionatore cloud: vedi l'installer o
[DOCKER.md](DOCKER.md).

Questa guida dice cosa serve, come installare driver e CUDA su **Ubuntu** (la strada provata) e su **Debian**, come
verificare e cosa fa poi l'installer. Ogni numero viene dalle misure del progetto (docs/MEASUREMENTS.md); quello che
non è misurato è scritto.

## 1. Quale GPU serve

Il ragionatore è **Qwen3.6-35B-A3B** quantizzato Q4_K_M: **20,6 GB** di pesi, un *mixture of experts* (256 esperti,
8 attivi per parola: per questo è veloce). Aurora sceglie da sola il profilo leggendo le GPU presenti
(`sys/core/script/sys_profile.py`):

| GPU | Profilo | Misurato? |
|---|---|---|
| **2 × 16 GB** o più (es. due RTX 5070 Ti / 4080 / 5080) | tutto in GPU, contesto 32k | ✅ macchina di riferimento: ~112 token/s |
| **1 × 24 GB** o più (es. RTX 3090 / 4090 / 5090) | tutto in GPU, qualche esperto in RAM per lasciare spazio a encoder e re-ranker | ⚠️ stima, non misurato |
| **1 × 16 GB** (es. RTX 4060 Ti 16 GB, 4080, 5070 Ti) | molti esperti in RAM (servono **48 GB di RAM** consigliati), risposte più lente | ⚠️ stima, non misurato |
| meno di 16 GB | ragionatore **cloud** (mascherato); ricerca, memoria e documenti restano sul computer | ✅ il profilo cloud |

Serve anche lo spazio: **45 GB liberi** per un'installazione con ragionatore locale (modelli obbligatori 24,7 GB, più
ambiente e compilazione). Con più schede Aurora usa le prime due da almeno 15 GB (nell'ordine di `nvidia-smi`); le altre restano libere.

Puoi controllare in anticipo un modello qualsiasi (anche diverso da Qwen) con
`.venv/bin/python sys/core/script/sys_model_check.py file.gguf`, o dalla pagina 🧠 Modelli → 🧩 *Un altro modello
locale*: dice se ci sta intero, con esperti in RAM, o non ci sta.

## 2. Ubuntu 26.04 / 24.04 (la strada provata)

Su Ubuntu **il driver viene da Ubuntu** (moduli firmati, precompilati per ogni kernel: niente compilazioni che si
rompono al prossimo aggiornamento) e **il toolkit CUDA da NVIDIA** (il più recente, accanto al driver). Lo script del
progetto fa tutto e, senza `--yes`, mostra soltanto cosa farebbe:

```bash
cd aurora                                   # la cartella del clone
sudo sys/core/script/sys_nvidia.sh check    # cosa c'è: driver, toolkit, schede, residui
sudo sys/core/script/sys_nvidia.sh driver --driver $(ubuntu-drivers devices 2>/dev/null | awk '/recommended/{print $3}' | sed 's/nvidia-driver-//') --yes
sudo reboot
sys/core/script/sys_nvidia.sh verify        # dopo il riavvio: nvidia-smi vede le schede
sudo sys/core/script/sys_nvidia.sh toolkit --yes     # CUDA 13 da NVIDIA, senza toccare il driver
bash install.sh                             # vede la GPU e propone il ragionatore locale
```

Un *pin* di apt impedisce che il repository di NVIDIA installi pacchetti del driver: mescolare i driver di NVIDIA con
quelli di Ubuntu è il modo classico in cui un sistema perde le GPU. Tutto è registrato in `/var/log/aurora-nvidia.log`.

Se una scheda c'è ma `nvidia-smi` non la vede, l'installer lo dice e stampa il comando del driver consigliato.

## 3. Debian 13 (trixie) / 12 (bookworm)

`sys_nvidia.sh` è scritto per Ubuntu (usa `ubuntu-drivers` e i suoi moduli firmati): **su Debian driver e toolkit si
installano a mano**, poi l'installer trova `nvcc` e salta lo script. *Questa sezione non è ancora provata su una
macchina vera: il primo che la segue ce lo dica (🐞 Segnala un bug).*

**Driver (dai repository di Debian).** Abilita `contrib non-free non-free-firmware` in `/etc/apt/sources.list` (o nel
file `.sources` di Debian 13), poi:

```bash
sudo apt update
sudo apt install linux-headers-$(uname -r) nvidia-driver firmware-misc-nonfree
sudo reboot
nvidia-smi                                  # deve elencare le schede
```

Con *Secure Boot* attivo il modulo va firmato (Debian lo chiede durante l'installazione con DKMS, *MOK enroll*), oppure
Secure Boot va spento nel BIOS.

**Toolkit CUDA (da NVIDIA, ≥ 12.8: le schede RTX 50 «Blackwell» lo richiedono).** Dal sito di NVIDIA, *CUDA Toolkit →
Linux → x86_64 → Debian*, scegli la tua versione (se la 13 non c'è ancora, la 12) e il tipo *deb (network)*: installa
il `cuda-keyring` che ti indica, poi **solo il toolkit, mai il driver di NVIDIA**:

```bash
sudo apt update
sudo apt install --no-install-recommends cuda-toolkit-13-0     # il numero che il sito propone
sudo ln -sfn /usr/local/cuda-13.0 /usr/local/cuda               # se /usr/local/cuda non c'è già
/usr/local/cuda/bin/nvcc --version                              # «release 13.x» (o almeno 12.8)
```

Prima di confermare guarda l'elenco di apt: se compaiono pacchetti `nvidia-driver`, `cuda-drivers` o `libnvidia-*`,
fermati — vorrebbe sostituire il driver di Debian.

Poi `bash install.sh`: trova la GPU e `nvcc`, propone il ragionatore locale e compila llama.cpp per le tue schede.

## 4. Cosa fa l'installer con la GPU

1. legge le schede (`nvidia-smi`) e propone: **1) sulla tua GPU** (consigliato: niente esce) o **2) un modello cloud**;
2. controlla `nvcc ≥ 12.8`; su Ubuntu, se manca, installa il toolkit con `sys_nvidia.sh`;
3. scarica i modelli (Hugging Face, revisioni fissate, SHA-256 verificati);
4. compila **llama.cpp** per le architetture presenti (`sys/runtime/llama.cpp`);
5. scrive il profilo nel `.env` (`AURORA_LLM_GPUS`, `AURORA_LLM_TENSOR_SPLIT`, `AURORA_LLM_CPU_MOE_LAYERS`, `AURORA_LLM_CTX`);
6. avvia `aurora-llm` (il ragionatore), `aurora-models` (encoder e re-ranker sulla GPU) e gli altri servizi.

Una regola che Aurora rispetta da sola: **una GPU, un lavoro alla volta** — un sogno dipinto, un video o un cambio di
modello aspettano che la GPU sia libera.

## 5. Verifiche

```bash
nvidia-smi                                                     # schede, driver, memoria
/usr/local/cuda/bin/nvcc --version                             # toolkit
sys/runtime/llama.cpp/bin/llama-server --version               # llama.cpp compilato
.venv/bin/python sys/core/script/sys_profile.py                # il profilo scelto per questa macchina
.venv/bin/python sys/core/script/sys_doctor.py                 # tutto: servizi, funzioni, firma
```

Nella WebUI: 📊 Stato (i servizi) e 🧠 Modelli (chi fa cosa, e il modello locale in uso).

## 6. E le schede AMD Radeon?

Oggi **no**: Aurora è costruita e misurata su NVIDIA (CUDA). La strada esiste — llama.cpp funziona anche con **ROCm**
(HIP) e con **Vulkan**, PyTorch ha build ROCm per encoder e re-ranker — ma nessuno del progetto ha una Radeon per
provarla, e qui non si scrive niente che non sia misurato. Se ne hai una e vuoi aiutare: apri una issue
(💡 Segnala un'idea) con modello della scheda, VRAM, distribuzione e l'uscita di `vulkaninfo --summary` e
`rocminfo` (se installato): è il primo passo per un profilo AMD (ROADMAP, riga 80).
