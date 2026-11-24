# Getting started — primo device, primo messaggio

## In 5 minuti

1. **Login** su `http://<IP-Pi>:8080` (utente `admin` + password del setup)
2. **Menu → Analizzatori → + Aggiungi device**
3. **Passo 1**: scegli **USB** o **TCP** in base a come è collegato
4. **Passo 2**: porta seriale (USB) o porta di ascolto (TCP)
5. **Passo 3**: ID + display name + protocollo
6. Salva con `enabled: false`
7. **Menu → Trace protocollo**: seleziona il device
8. Fai partire un campione sull'analizzatore → dovresti vedere i frame in trace
9. Se OK: torna in Configurazione → Passo 4 → attiva il toggle
10. **Menu → Configurazione → Passo 3**: attiva il tuo PIS (Vitomed/Tomedo…)
11. **Test invio**: bottone accanto al target → devi vedere `succeeded: [<target>]`
12. Sei pronto — attivalo `enabled: true` sul target e vai in produzione

## Se qualcosa non funziona

- Vedi [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — flowchart per sintomo
- **Trace protocollo** ti fa vedere i byte reali che arrivano
- **Test invio** ti fa vedere se il PIS accetta un messaggio sintetico
- **Dead-letter queue** raccoglie i messaggi che nessun target ha accettato

## Prima del primo cliente reale

- ⚠️ **Verifica ogni device con hardware reale in staging** — le config nel
  catalogo sono template, alcune vanno adattate al modello specifico
- ⚠️ **Verifica il PIS in staging** — ogni installazione di Vitomed / Tomedo
  ha quirk (charset, MSH-3, campi obbligatori)
- ⚠️ **Firma la DPA** (Data Processing Agreement) con la clinica
- ⚠️ **Cambia il nome facility** — non lasciare `PRAXIS_NAME`
