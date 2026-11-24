# Configurazioni per studio

Qui sta la configurazione di ogni studio, **senza password**, sotto controllo
di versione.

## Perché esiste questa cartella

Fino a oggi la configurazione di produzione viveva solo dentro il Raspberry
Pi dello studio: `config/gateway.yaml`, escluso da git perché conteneva la
password SFTP. Conseguenze concrete, tutte già capitate:

- quando i referti hanno smesso di arrivare a Tomedo, non c'era modo di
  confrontare la configurazione di quel giorno con quella della settimana
  prima. La diagnosi è durata due giorni;
- l'unica copia del file era su una scheda SD;
- nessuno poteva rispondere a "cosa è cambiato?".

Ora i segreti stanno fuori dal file, in `config/secrets.env`, e il resto
della configurazione può essere versionato.

## Come funziona

Nel file dello studio si dichiara **il nome della variabile d'ambiente**, non
la password:

```yaml
targets:
  - name: tomedo
    type: tomedo
    sftp_user: jerumed
    sftp_pass_env: TOMEDO_SFTP_PASS    # il valore sta in secrets.env
```

Sul Raspberry, in `/opt/jerumednexus/config/secrets.env`:

```
TOMEDO_SFTP_PASS=la-password-vera
```

Le unit systemd caricano già quel file (`EnvironmentFile=`), quindi non
serve altro. Se la variabile manca, **il gateway non parte** e lo dice: è
voluto. Partire con una password vuota significherebbe accumulare referti in
coda senza che nessuno capisca perché.

`secrets.env` resta escluso da git, e deve restarci.

## Installare la configurazione di uno studio

```bash
sudo cp deploy/studi/<studio>.yaml /opt/jerumednexus/config/gateway.yaml
sudo nano /opt/jerumednexus/config/secrets.env    # le password
sudo systemctl restart jerumednexus-gateway
```

Poi, dalla WebUI, apri **Verifica impianto**: dice in pochi secondi se la
catena è intera.

## Regola

**Non si modificano i file direttamente sul Raspberry.** Una modifica fatta
lì sparisce al primo aggiornamento e non lascia traccia di cosa è cambiato.
Si modifica qui, si committa, e si porta sul Pi.
