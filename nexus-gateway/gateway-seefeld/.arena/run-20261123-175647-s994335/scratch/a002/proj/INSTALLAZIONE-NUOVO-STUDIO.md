# Installare JerumedNexus in uno studio nuovo

Guida completa, dal Raspberry spento al primo referto assegnato in Tomedo.

Ogni avvertenza qui dentro nasce da un guasto vero. Tutti avevano lo stesso
sintomo: **niente**. Nessun errore, nessun messaggio, i referti semplicemente
non arrivavano. Leggi i riquadri: sono le ore risparmiate.

---

## Prima di cominciare

Serve:

- un Raspberry Pi con Raspberry Pi OS aggiornato e collegato alla rete dello studio
- l'indirizzo IP del server del gestionale (per Tomedo: il Mac)
- utente e password SFTP del gestionale
- **il nome del medico** a cui vanno intestati i referti
- gli analizzatori collegati: via USB, oppure via cavo di rete

Annota per ogni analizzatore **come è collegato**. È la domanda che fa perdere
più tempo: un apparecchio in rete non si trova con la scansione USB, e uno in
USB non ha una porta di ascolto.

---

## 1. Copiare il pacchetto sul Raspberry

Dal tuo computer:

```bash
scp nexus-gateway.zip UTENTE@INDIRIZZO_PI:~/
```

`UTENTE` è il nome con cui fai `ssh` (spesso `pi`). Se l'indirizzo non viene
risolto, aggiungi `.local` al nome del Raspberry, oppure usa l'IP numerico.

---

## 2. Installare

Sul Raspberry:

```bash
cd ~ && unzip -o nexus-gateway.zip && sudo ./gateway-seefeld/scripts/install.sh
```

L'installazione chiede tre cose:

| Domanda | Cosa rispondere |
|---|---|
| Nome della clinica/studio (MSH-4) | il nome dello studio |
| Destinatario, di solito il medico (MSH-6) | **il nome del medico** |
| Password amministratore Web UI | almeno 12 caratteri |

> **MSH-4 e MSH-6 sono due cose diverse**: da chi arriva il referto, e a chi è
> indirizzato. Scrivere lo stesso nome in entrambi fa sì che il gestionale
> riceva i file, li legga, e non li assegni a nessun paziente. Due giorni di
> diagnosi, la prima volta.

Alla fine stampa l'indirizzo della WebUI. Annotalo.

---

## 3. Aprire le porte degli analizzatori in rete

```bash
sudo /opt/jerumednexus/scripts/firewall-sync.sh
```

> Il firewall è in *default deny*. Un analizzatore in rete invia, il kernel
> scarta il pacchetto, e **nei log del gateway non compare niente** — identico
> a un cavo staccato. Vai rieseguito **ogni volta che aggiungi un analizzatore
> in rete**, perché la WebUI gira senza privilegi e non può aprire porte.

---

## 4. Primo accesso

Apri l'indirizzo nel browser e crea l'utente **tecnico** (amministratore).
Da lì, in *Utenti*, crei poi quello del **medico**, che vede i referti e può
rispedirli ma non tocca la configurazione.

---

## 5. Configurare il gestionale destinatario

**Configurazione → Passo 3 — Gestionali destinatari.**

Accendi quello dello studio e compila i campi. Per Tomedo: indirizzo del Mac,
porta 22, utente e password SFTP, cartella remota (di solito
`/Users/<utente>/ldt`).

Poi, nella stessa pagina, controlla **Passo 2 — Identità HL7**:

| Campo | Valore |
|---|---|
| Versione HL7 | `2.3` |
| Codifica | `8859/1` |
| Fuso orario nei timestamp | **spento** |

> `2.3` e `8859/1` sono il formato che Tomedo importa davvero, verificato
> contro un file archiviato e assegnato. Con `2.5` e UTF-8 archivia il file e
> lo rifiuta. Il fuso orario aggiunge `+0200` alle date e fa smettere a Tomedo
> di riconoscere i referti.

---

## 6. Configurare gli analizzatori

**Configurazione → Passo 4 — Altri analizzatori → + Aggiungi device.**

### Se è collegato via USB

Scegli il collegamento **USB** e la porta seriale. Usa sempre il percorso
stabile che compare nell'elenco, del tipo `/dev/jerumednexus/ftdi-XXXX`.

> **Mai** `/dev/ttyUSB0`. A ogni riavvio il kernel rinumera le porte nell'ordine
> in cui le trova: due adattatori si scambiano di posto e l'apparecchio
> "sparisce" pur essendo attaccato. I percorsi stabili contengono il numero di
> serie dell'adattatore e non cambiano.

### Se è collegato via cavo di rete

Scegli il collegamento **TCP**, indica la porta di ascolto e, per i Sysmex,
la modalità ASTM.

| Analizzatore | Porta | Modalità |
|---|---|---|
| Sysmex XQ-320 | 5006 | `1381-95` |
| altri Sysmex | 5006 | `1381-02` se non sai |

> Il XQ-320 non fa la stretta di mano ENQ/ACK: manda i record grezzi. Con la
> modalità sbagliata il gateway aspetta un segnale che non arriva mai e non
> registra nulla.

> **Non modificare un apparecchio per cambiargli collegamento**: eliminalo e
> ricrealo. La modifica può lasciare dentro i campi del collegamento vecchio, e
> il lettore guarda **prima** la porta seriale — un apparecchio "in TCP" con un
> `serial_port` residuo apre il cavo USB e la porta di rete resta muta.

Dopo aver aggiunto un apparecchio in rete, riesegui `firewall-sync.sh`.

---

## 7. La parte da fare nel gestionale

**Questo il gateway non può farlo.** Senza, i referti arrivano e restano non
assegnati.

In Tomedo: **Verwaltung → Laboreingang / Labordatentransfer → Praxis →
Laborimport → HL7 Befundzuordnung am Server**, campo
*«HL7, für folgende SendingApplications werden neue Aufträge erstellt»*.

Vanno aggiunti i nomi con cui il gateway si presenta, cioè il campo MSH-3 di
ogni referto: **il nome visualizzato di ogni analizzatore**.

> I nomi devono coincidere **carattere per carattere**, maiuscole e trattini
> compresi. Per Tomedo `LOC200` e `LOC-200` sono due stringhe diverse, e la
> seconda non corrisponde a niente.

Per sapere con che nome sta arrivando un referto: **Frame Inspector** → apri un
campione → terzo campo della riga `MSH`.

---

## 8. Verificare

**Verifica impianto → Esegui la verifica.**

Controlla in pochi secondi: il servizio, l'identità HL7, ogni analizzatore
configurato, ogni destinatario raggiungibile, lo spazio su disco. I guasti
compaiono per primi, con il rimedio accanto.

Poi manda un test da ogni analizzatore e guarda il **Frame Inspector**: deve
comparire una riga per ciascuno con stato `OK`.

Infine controlla in Tomedo che il referto sia stato **assegnato al paziente**,
non solo ricevuto.

---

## Se qualcosa non arriva

In ordine, perché ognuno esclude il precedente.

**Il referto non compare nel Frame Inspector** — non è arrivato al gateway.
Analizzatore spento, cavo staccato, oppure porta chiusa nel firewall:
riesegui `firewall-sync.sh`. Per un apparecchio in rete, verifica che qualcuno
ascolti davvero:

```bash
sudo ss -lntp | grep LA_PORTA
```

**Compare con stato ERRORE** — è arrivato ma la consegna è fallita. Il motivo
è in *Da rispedire*, colonna Motivo, oppure:

```bash
sudo journalctl -u jerumednexus-gateway -n 50 --no-pager
```

Nessun referto è perso: restano in coda e si rispediscono dalla stessa pagina.

**Compare OK ma Tomedo non lo assegna** — è arrivato e consegnato, ma il
gestionale non crea l'ordine. Quasi sempre è il nome del mittente che non
corrisponde: vedi il punto 7.

---

## Manutenzione

```bash
# stato dei servizi
systemctl status jerumednexus-gateway jerumednexus-webui --no-pager

# riavvio (non serve dopo un cambio di configurazione: viene riletta da sola)
sudo systemctl restart jerumednexus-gateway jerumednexus-webui

# copia di sicurezza — contiene licenza, utenti, password e coda
sudo tar czf ~/backup-gateway-$(date +%F).tgz -C /opt/jerumednexus config logs
```

Fai la copia **prima** di ogni aggiornamento. La licenza non si può ricreare.

Per aggiornare senza perdere niente:

```bash
cd ~ && unzip -o nexus-gateway.zip && sudo ./gateway-seefeld/scripts/install.sh --upgrade
```

`--upgrade` conserva configurazione, log, licenza, utenti e le scelte fatte
nella pagina Analizzatori.

---

## Una regola

**Non modificare i file direttamente sul Raspberry.** Una modifica fatta lì
sparisce al primo aggiornamento e non lascia traccia di cosa è cambiato. La
configurazione si cambia dalla WebUI; il codice si aggiorna con un pacchetto
nuovo.
