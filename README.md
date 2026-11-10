# Project Ingenuity

Dashboard FastAPI, video Picamera2/IMX708 e tracking selezionato dall'utente con gimbal a servo **a rotazione continua**. L'implementazione attiva è in `ingenuity/`; `app.main:app` è un alias del server. Nessun dispositivo viene aperto importando il server.

## Installazione sul Raspberry Pi

Usare un sistema con Picamera2/libcamera funzionanti e Python >= 3.11. Su Raspberry Pi OS installare Picamera2 dai pacchetti di sistema, evitando copie libcamera incompatibili dal package manager Python:

```bash
sudo apt update
sudo apt install python3-picamera2 python3-venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Inserire il valore generato in `JWT_SECRET` e impostare una password non vuota in `ROBOT_PASSWORD`. È supportato anche `ROBOT_PASSWORD_HASH` (Argon2), che ha precedenza sulla password in chiaro. `.env` rimane escluso da Git. Abilitare I²C e verificare che il dispositivo PCA9685 sia collegato correttamente prima del test gimbal.

`requirements.txt` usa le dipendenze dichiarate in `pyproject.toml`, senza il vecchio elenco di pacchetti CUDA/NVIDIA. Non installare contemporaneamente le varianti `opencv-python` e `opencv-python-headless` nello stesso ambiente: espongono entrambe `cv2`. Ultralytics richiede comunque PyTorch; verificare disponibilità dei pacchetti ARM64 e spazio libero. L'installazione hardware completa non è verificabile su un host privo del Raspberry.

## Modello NCNN

I pesi sono esclusi da Git. Esportare un modello compatibile con la versione Ultralytics installata, anche su un altro computer, e copiare **l'intera directory** nel repository:

```bash
yolo export model=yolo26n.pt format=ncnn imgsz=320
```

Sono necessari `model.ncnn.param`, `model.ncnn.bin` e `metadata.yaml` dentro `yolo26n_ncnn_model/`. In alternativa impostare `YOLO_MODEL_PATH` a un percorso assoluto. `YOLO_IMGSZ` deve corrispondere alle dimensioni quadrate dell'esportazione. Il codice verifica i metadati e mantiene il video disponibile con IA offline se il modello manca o è incompatibile.

La pipeline passa il frame BGR pulito a Ultralytics, che preserva il rapporto d'aspetto e restituisce coordinate sull'immagine originale. `INFERENCE_INTERVAL=0.25` indica l'intervallo minimo tra gli inizi delle inferenze, non garantisce 4 FPS sul Raspberry. Se il tempo d'inferenza supera 1,5 secondi, il risultato viene scartato e la gimbal resta ferma. `python ncnn_benchmark.py` misura il percorso reale di inferenza, includendo preprocessing e postprocessing.

## Avvio

Dalla directory del progetto:

```bash
source .venv/bin/activate
python main.py
# equivalente:
python -m uvicorn ingenuity.web.server:app --host 0.0.0.0 --port 8000 --workers 1
```

Usare **un solo processo worker**, senza `--reload` quando si controlla l'hardware. La camera e la gimbal appartengono al lifespan del server e vengono rilasciate allo spegnimento. Un errore hardware lascia disponibile la dashboard autenticata per la diagnosi. Se si usa HTTPS impostare `COOKIE_SECURE=1`; per HTTP locale resta `0`. Configurare correttamente il proxy fidato se HTTPS termina a monte.

## Tracking gimbal

- PAN sul canale **0**, TILT sul canale **1**. Neutri iniziali: **1558 µs** e **1600 µs**, configurabili tramite `.env`.
- `pan()` e `tilt()` ricevono una **velocità normalizzata tra -1 e +1**, mai un angolo. Valori non finiti o fuori intervallo vengono rifiutati. `center()` invia il neutro, non posiziona il servo.
- La dashboard invia indice **e versione** dell'elenco. Se l'elenco è cambiato o è scaduto, la selezione viene rifiutata, la gimbal fermata e viene richiesto di selezionare di nuovo.
- Il bersaglio viene associato per classe, distanza e variazione di dimensione. Se due candidati sono troppo simili, il sistema si ferma anziché scegliere arbitrariamente. Non è un identificatore biometrico o una garanzia d'identità durante occlusioni/incroci.
- Controllo proporzionale a 50 Hz, velocità massima 0,10, accelerazione limitata, isteresi centrale (6% ingresso / 9% uscita del semiasse).
- Ogni nuova detection autorizza **al massimo 180 ms** di movimento. Poi il servo torna al neutro finché non arriva un'altra osservazione valida. Questo riduce sovracorrezioni e impedisce il mantenimento indefinito del comando quando YOLO si arresta.
- La freschezza è misurata dall'acquisizione del frame, includendo il tempo d'inferenza. STOP e comandi vengono serializzati; dopo la risposta STOP non vengono emessi nuovi movimenti senza un'altra selezione.
- `LOST` ferma subito gli assi. Una breve riacquisizione è ammessa entro 1 secondo dall'ultima osservazione valida; oltre serve una nuova selezione.
- `PAN_DIRECTION=-1` mantiene il verso del codice precedente. Invertire a `1` se il movimento allontana il bersaglio dal centro.
- `TRACK_TILT_ENABLED=0` per impostazione predefinita. Abilitare il TILT solo dopo aver calibrato neutro e verso con `TILT_DIRECTION` e verificato la corsa libera del montaggio.

Questi servo non forniscono posizione assoluta: il software non può conoscere i finecorsa o il numero di giri dei cavi senza sensori aggiuntivi. I limiti temporali software non sostituiscono un arresto hardware in caso di processo bloccato, guasto I²C o alimentazione anomala.

### Prova sul robot

1. Arrestare eventuali altre istanze del server. Liberare la corsa dei cavi e sostenere la camera.
2. Eseguire `python test_neutral.py`: entrambi gli assi devono restare fermi. Regolare i neutri prima di procedere.
3. Avviare il server, accedere e selezionare un oggetto isolato. Verificare il verso PAN con il bersaglio poco fuori centro.
4. Premere STOP: conferma `IDLE` e assi fermi. Nascondere il bersaglio: deve comparire `LOST` e cessare il movimento.
5. Valutare oscillazioni e tempo d'inferenza; solo dopo abilitare eventualmente il TILT. Non aumentare velocità e durata degli impulsi prima di aver misurato il comportamento reale.

I file `test_*.py` alla radice e in `tests/` sono **prove manuali**, eseguibili esplicitamente e protette dal guard `__main__`. `test_pan_tracking.py` usa lo stesso controllore del server; non eseguirlo insieme al server. Le copie `.bak`, `.backup` e `.before-*` sono storiche e non vengono importate. `tracking_phase1.patch` è una proposta storica già superata, non una patch da applicare al codice attuale.

## Test automatici senza hardware

In un ambiente di sviluppo separato:

```bash
python -m pip install -e '.[test]'
python -m pytest
node --check ingenuity/static/js/dashboard.js
```

La suite predefinita è `tests/unit/`: camera, modello e gimbal simulati, autenticazione HTTP/WebSocket, selezioni obsolete, timeout, isteresi, STOP, pulizia risorse e salvataggio foto. Non apre periferiche reali. La convalida su IMX708, NCNN ARM64 e servi resta un passaggio distinto.

Documentazione di riferimento: [Picamera2](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf), [Ultralytics predict](https://docs.ultralytics.com/modes/predict/), [export NCNN](https://docs.ultralytics.com/modes/export/), [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).


### Calibrazione hardware verificata il 8 novembre 2026

Sul PCA9685 di questo robot il clock di riferimento e impostato a 27.750.000 Hz:
con il valore nominale di 25 MHz un impulso richiesto da 1500 us misurava circa
1350 us. La misura Arduino dopo correzione e circa 1494–1501 us. Entrambi i servo
sono fermi a 1500 us. STOP disabilita il PWM, comportamento verificato sui servo
installati; non garantisce coppia di mantenimento o arresto in caso di bus guasto.
Questa calibrazione e specifica dell'hardware, non universale.

Il pan usa attualmente 1550 us nel verso positivo e 1415 us nel negativo. La durata
e proporzionale all'errore (vedi taratura sotto) e torna al minimo dopo un'inversione.
Ogni movimento termina senza estensioni dovute a nuove detection. Prima di un
altro movimento serve un'immagine acquisita almeno 60 ms dopo l'arresto.
La zona centrale e l'isteresi restano attive. Le temporizzazioni dipendono dallo
scheduling Linux: non sono un arresto hardware garantito. Tilt disabilitato di
default: non e stata misurata la sua risposta nei due versi.

SEGUI risolve l'indice nel lotto originale mostrato dalla dashboard (storico
limitato a 32 lotti), ne verifica la freschezza e associa il bersaglio al lotto
corrente per classe, posizione e dimensioni. Rifiuta associazioni ambigue e dati
scaduti, senza annullare un inseguimento gia attivo. Nessun retry automatico
applica lo stesso indice a un lotto diverso. La grazia di riaggancio decorre dalla
perdita del bersaglio, non dall'acquisizione dell'ultima immagine valida.

Validazione software: test con clock, camera e servo simulati. Il controllo a
impulsi brevi richiede ancora verifica fisica di verso, overshoot e STOP sul robot.


### Riaggancio dopo detection intermittenti

La finestra di riaggancio e 3 secondi dalla prima perdita. Durante LOST i motori
restano fermi; non si allunga la validita delle immagini (sempre 1,5 secondi).
Oltre al limite di centro di 180 pixel, una detection della stessa classe puo
corrispondere se IoU >= 0,25 e lo spostamento non supera il 60% della diagonale
del riquadro precedente. Il filtro di rapporto delle aree resta 0,4–2,5.
Se piu candidati sono plausibili e uno richiede il criterio esteso, l'associazione
viene rifiutata. Sono euristiche geometriche, non identificazione della persona:
incroci e occlusioni possono ancora richiedere una selezione manuale.


### Stabilizzazione attorno al centro

Il pan usa la mediana degli ultimi tre errori normalizzati ammissibili. Servono
tre osservazioni coerenti sullo stesso lato vicino al centro (errore < 0,25),
due piu lontano. La stessa versione non viene contata due volte. STOP, perdita
e fine movimento azzerano le evidenze; un attraversamento del centro ripristina
l'isteresi di uscita. Per le persone grandi la zona centrale viene adattata come descritto sotto. Il filtro aggiunge
latenza dipendente dagli FPS di inferenza e deve essere verificato sul robot.


### Taratura a passi piu piccoli

Durata aggiornata: 20–35 ms in senso antiorario (1415 us) e 20–26,25 ms
in senso orario (1550 us). Restano la conferma temporale delle detection,
l'attesa di 60 ms dopo l'arresto e la richiesta di una nuova immagine successiva
all'attesa. Nessun movimento viene prolungato dall'arrivo di altre detection.
Questi sono tempi richiesti al software, non misure dello spostamento angolare:
la risposta meccanica e i ritardi dello scheduling vanno verificati sul robot.

### Persone vicine e riquadri tagliati (10 novembre 2026)

Per la classe person, la tolleranza del pan cresce gradualmente quando la larghezza
del riquadro passa dal 35% al 75% dell'immagine. Le soglie di ingresso/uscita
passano da 0,06/0,09 a 0,12/0,15, normalizzate rispetto alla meta della larghezza:
a 960 px sono rispettivamente circa 29/43 px e 58/72 px. La dimensione del riquadro
e solo un indicatore euristico, non una misura della distanza.

Se il riquadro arriva entro il 2% di un bordo laterale, il movimento viene sospeso,
anche durante un impulso. Il bersaglio resta selezionato finche il tracker lo
riconosce; la dashboard segnala la pausa. Il filtro viene azzerato e la ripresa
richiede nuove osservazioni coerenti con il riquadro di nuovo interno ai bordi.
Non si tenta di recuperare automaticamente una persona parzialmente fuori campo:
puo essere necessario che rientri o si allontani dalla camera. Il centro usato
resta quello del riquadro, non quello anatomico del corpo.

Restano invariati STOP, freschezza dei dati, velocita calibrate (1415/1550 us),
durate massime e pausa dopo ogni movimento. Test software con camera e servo
simulati verificano oscillazioni dei riquadri grandi, bordi, arresto durante un
impulso, ripresa e altre classi. La resa fisica richiede una prova sul robot.
