Markdown

# ✉️ MailCleaner

> Un outil automatisé et performant de nettoyage de boîte mail IMAP, de désabonnement aux newsletters et de routage intelligent de dossiers, développé en Python. Zéro éditeur de code requis : tout se configure directement dans votre terminal.

---

## 🛠️ Guide d'installation complet (Pour débutants)

Aucun logiciel n'est nécessaire. Suivez simplement ces étapes dans votre terminal :

### Étape 1 : Ouvrir le Terminal sur Mac
1. Appuyez sur **Cmd + Espace** pour ouvrir la recherche Spotlight.
2. Tapez **Terminal** et appuyez sur **Entrée**.

### Étape 2 : Installer Homebrew (Le gestionnaire de logiciels)
Copiez-collez cette commande dans votre terminal et appuyez sur Entrée :
```bash
/bin/bash -c "$(curl -fsSL [https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh](https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh))"

Étape 3 : Installer Python

Une fois Homebrew installé, installez Python avec cette commande :
Bash

brew install python

Étape 4 : Télécharger le projet

Téléchargez le dépôt (bouton vert Code > Download ZIP) et dézippez-le sur votre Bureau. Ensuite, dans le terminal, tapez cd  (avec un espace après) et glissez-déposez le dossier dézippé depuis votre bureau directement dans la fenêtre du terminal, puis appuyez sur Entrée.
Étape 5 : Créer l'environnement isolé et installer la dépendance

Copiez-collez ces lignes dans votre terminal :
Bash

python3 -m venv venv
source venv/bin/activate
pip install requests

🔑 Obtenir son mot de passe d'application (Gmail)

    Allez sur les paramètres de sécurité Google : myaccount.google.com/security.

    Activez la Validation en deux étapes.

    Dans la barre de recherche en haut, tapez : Mots de passe des applications.

    Créez un nom (ex: MailCleaner) et copiez le code à 16 lettres sans espaces.

🚀 Utilisation

Lancez simplement le script pour la première fois. Le terminal vous demandera automatiquement votre e-mail et votre mot de passe d'application, puis générera votre configuration tout seul :
1. Mode Simulation (Recommandé pour tester sans risque)
Bash

python3 cleaner.py --dry-run

2. Nettoyage réel
Bash

python3 cleaner.py

🔒 Sécurité

Le fichier config.json qui stocke vos identifiants est généré localement et automatiquement exclu de Git grâce au fichier .gitignore pour éviter toute fuite sur GitHub.
📄 Licence

Distribué sous la licence MIT.