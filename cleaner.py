import imaplib
import email
import re
import os
import sys
import json
import signal
import argparse
import logging
import requests
import warnings
from concurrent.futures import ThreadPoolExecutor
from email.header import decode_header

# Masque l'avertissement lié à LibreSSL sur macOS
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

LOG_UIDS_FILE = "processed_uids.txt"
LOG_DOMAINS_FILE = "unsubscribed_domains.txt"
CONFIG_FILE = "config.json"

def decode_header_value(header_val):
    if not header_val:
        return ""
    decoded_fragments = decode_header(header_val)
    text = ""
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            text += fragment.decode(encoding or 'utf-8', errors='ignore')
        else:
            text += str(fragment)
    return text

class MailCleaner:
    def __init__(self, config_path, dry_run=False):
        self.dry_run = dry_run
        self.config = self.load_or_create_config(config_path)
        self.processed_uids = self.load_set_from_file(LOG_UIDS_FILE)
        self.unsubscribed_domains = self.load_set_from_file(LOG_DOMAINS_FILE)
        self.mail = None
        self.trash_batch = []
        
        signal.signal(signal.SIGINT, self.graceful_exit)
        signal.signal(signal.SIGTERM, self.graceful_exit)

    def load_or_create_config(self, path):
        """Si le fichier config.json n'existe pas, le terminal interroge l'utilisateur."""
        if not os.path.exists(path):
            print("\n--- 🛠️ Assistant de configuration initial ---")
            print("Aucun fichier de configuration détecté. Répondez aux questions ci-dessous :\n")
            
            email_input = input("Entrez votre adresse e-mail (ex: vous@gmail.com) : ").strip()
            # Utilisation d'un input classique pour autoriser le copier-coller (Cmd + V) du mot de passe d'application
            password_input = input("Entrez votre mot de passe d'application (16 caractères sans espaces) : ").strip()

            config_data = {
                "email": email_input,
                "password": password_input,
                "imap_server": "imap.gmail.com",
                "trash_folder": "\"[Gmail]/Corbeille\"",
                "batch_size": 50,
                "whitelist": [
                    "github.com",
                    "urssaf.fr",
                    "gouv.fr",
                    "laposte",
                    "identitenumerique"
                ],
                "protected_keywords": [
                    "code",
                    "verification",
                    "password",
                    "facture",
                    "suivi"
                ],
                "alias_routing": {}
            }

            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
                print(f"\n[succès] Fichier '{path}' généré automatiquement avec vos informations.\n")
            except Exception as e:
                logging.error(f"Impossible d'écrire le fichier de configuration : {e}")
                sys.exit(1)

            return config_data

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_set_from_file(self, filepath):
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def append_to_file(self, filepath, value):
        if not self.dry_run:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"{value}\n")

    def connect(self):
        logging.info("Connexion SSL au serveur IMAP...")
        self.mail = imaplib.IMAP4_SSL(self.config["imap_server"])
        self.mail.login(self.config["email"], self.config["password"])
        self.mail.select("inbox")
        logging.info("Authentification réussie.")

    def is_whitelisted(self, from_header):
        from_lower = str(from_header).lower()
        return any(wl.lower() in from_lower for wl in self.config.get("whitelist", []))

    def has_protected_keyword(self, subject_header):
        subj = decode_header_value(subject_header).lower()
        return any(kw.lower() in subj for kw in self.config.get("protected_keywords", []))

    def parse_unsubscribe_header(self, msg):
        unsub_header = msg.get("List-Unsubscribe")
        post_header = msg.get("List-Unsubscribe-Post")

        if not unsub_header:
            return (None, None, False)

        is_one_click = post_header and "List-Unsubscribe=One-Click" in str(post_header)
        val = str(unsub_header)
        
        http_match = re.search(r'<(https?://[^>]+)>', val)
        if http_match:
            return ('http', http_match.group(1), is_one_click)

        mailto_match = re.search(r'<(mailto:[^>]+)>', val)
        if mailto_match:
            return ('mailto', mailto_match.group(1), False)

        return (None, None, False)

    def trigger_unsubscribe(self, proto, target, is_one_click, domain):
        if self.dry_run:
            logging.info(f"[SIMULATION] Désabonnement {proto.upper()} pour {domain}")
            return

        try:
            if proto == 'http':
                if is_one_click:
                    requests.post(
                        target,
                        data={'List-Unsubscribe': 'One-Click'},
                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        timeout=5
                    )
                    logging.info(f"Désabonnement RFC 8058 (POST) -> {domain}")
                else:
                    requests.get(target, timeout=5)
                    logging.info(f"Désabonnement HTTP (GET) -> {domain}")
        except Exception as e:
            logging.warning(f"Échec désabonnement {domain} : {e}")

    def flush_trash_batch(self):
        if not self.trash_batch:
            return
        uids_str = ",".join(self.trash_batch)
        if self.dry_run:
            logging.info(f"[SIMULATION] {len(self.trash_batch)} mails seraient envoyés à la corbeille.")
        else:
            self.mail.uid('copy', uids_str, self.config["trash_folder"])
            self.mail.uid('store', uids_str, '+FLAGS', '\\Deleted')
            logging.info(f"Batch de {len(self.trash_batch)} mails déplacé vers la corbeille.")
        self.trash_batch.clear()

    def graceful_exit(self, signum, frame):
        logging.warning("\nArrêt manuel (Ctrl+C). Sauvegarde de l'état...")
        if self.trash_batch:
            self.flush_trash_batch()
        if self.mail:
            try:
                self.mail.expunge()
                self.mail.logout()
            except Exception:
                pass
        logging.info("Connexion fermée proprement.")
        sys.exit(0)

    def run(self):
        self.connect()

        status, messages = self.mail.uid('search', None, 'HEADER List-Unsubscribe ""')
        uids = messages[0].split()
        
        logging.info(f"{len(uids)} newsletters potentielles détectées dans Inbox.")
        if self.dry_run:
            logging.info("--- MODE DRY-RUN ACTIF (Aucune modification ne sera enregistrée) ---")

        batch_size = self.config.get("batch_size", 50)

        with ThreadPoolExecutor(max_workers=5) as executor:
            for uid in uids:
                uid_str = uid.decode('utf-8')
                
                if uid_str in self.processed_uids:
                    continue

                res, msg_data = self.mail.uid('fetch', uid, '(BODY.PEEK[HEADER])')

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        msg_from = msg.get("From", "")
                        msg_to = msg.get("To", "")
                        msg_subject = msg.get("Subject", "")

                        domain_match = re.search(r'@([\w.-]+)', str(msg_from))
                        domain_str = domain_match.group(1).lower() if domain_match else ""

                        if self.is_whitelisted(msg_from):
                            self.append_to_file(LOG_UIDS_FILE, uid_str)
                            continue

                        if self.has_protected_keyword(msg_subject):
                            logging.info(f"Mail protégé (Sujet sensible) [UID {uid_str}]")
                            self.append_to_file(LOG_UIDS_FILE, uid_str)
                            continue

                        routed = False
                        for alias, target_folder in self.config.get("alias_routing", {}).items():
                            if alias in str(msg_to):
                                if not self.dry_run:
                                    self.mail.uid('copy', uid_str, target_folder)
                                    self.mail.uid('store', uid_str, '+FLAGS', '\\Deleted')
                                logging.info(f"[{alias}] Mail UID {uid_str} routé -> {target_folder}")
                                routed = True
                                break

                        if routed:
                            self.append_to_file(LOG_UIDS_FILE, uid_str)
                            continue

                        proto, target, is_one_click = self.parse_unsubscribe_header(msg)
                        
                        if target and domain_str not in self.unsubscribed_domains:
                            executor.submit(self.trigger_unsubscribe, proto, target, is_one_click, domain_str)
                            self.unsubscribed_domains.add(domain_str)
                            self.append_to_file(LOG_DOMAINS_FILE, domain_str)

                        self.trash_batch.append(uid_str)
                        if len(self.trash_batch) >= batch_size:
                            self.flush_trash_batch()

                        self.append_to_file(LOG_UIDS_FILE, uid_str)

        self.flush_trash_batch()
        if not self.dry_run:
            self.mail.expunge()
        self.mail.logout()
        logging.info("Exécution terminée.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MailCleaner - Script de nettoyage IMAP optimisé")
    parser.add_argument("-c", "--config", default="config.json", help="Chemin vers le fichier de configuration")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Simule l'exécution sans supprimer ni désabonner")
    args = parser.parse_args()

    cleaner = MailCleaner(config_path=args.config, dry_run=args.dry_run)
    cleaner.run()