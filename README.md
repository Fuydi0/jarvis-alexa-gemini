# Jarvis — Alexa + Gemini

Une skill Alexa qui transforme tes Echo en assistant vocal Gemini, en
français, gratuitement.

```
"Alexa, ouvre Jarvis"
"Jarvis à ton écoute. Pose ta question."
"Je veux partir à Lisbonne combien ça va me coûter ?"
```

## Pourquoi

Les Echo récents (Dot 3/4/5) ne sont pas jailbreakables. Le moteur de
recherche d'Alexa est dépassé face aux LLM. Cette skill remplace le
cerveau d'Alexa par Gemini, sans toucher au hardware.

C'est un fork francophone de [k4l1sh/alexa-gpt](https://github.com/k4l1sh/alexa-gpt)
avec Gemini au lieu d'OpenAI, et un mode conversation naturelle (pas de
préfixe à apprendre).

## Prérequis

- Compte Amazon Developer ([developer.amazon.com](https://developer.amazon.com/alexa/console/ask))
- Compte Google + clé API Gemini ([aistudio.google.com](https://aistudio.google.com/app/apikey))
- Un Echo

Tout est gratuit.

## Installation

### 1. Récupérer une clé API Gemini

[aistudio.google.com](https://aistudio.google.com) → **Get API key** →
**Create API key** → copie la clé.

![Récupérer une clé API](images/api_key.png)

### 2. Créer la skill

[developer.amazon.com/alexa/console/ask](https://developer.amazon.com/alexa/console/ask)
→ **Create Skill**.

- Skill name : `Jarvis`
- Locale : `French (FR)`
- Type : Custom

![Nommer la skill](images/name_your_skill.png)

- Hosting : **Alexa-Hosted (Python)**

![Hosting](images/hosting_services.png)

- Template : **Start from Scratch**

![Template](images/select_template.png)

### 3. Importer le modèle

Onglet **Build** → **JSON Editor** → remplace tout par le contenu de
[models/fr-FR.json](models/fr-FR.json) → **Save Model** → **Build Skill**.

![JSON Editor](images/intents_json_editor.png)

Le warning sur la carrier phrase est normal, ignore-le.

### 4. Déployer le code

Onglet **Code** :

- Remplace `lambda_function.py` par [lambda/lambda_function.py](lambda/lambda_function.py)
- Remplace `requirements.txt` par [lambda/requirements.txt](lambda/requirements.txt)
- Ligne 31 : remplace `YOUR_API_KEY` par ta vraie clé Gemini
- **Save** → **Deploy**

### 5. Tester

Onglet **Test** → passe en **Development**.

![Development](images/development_enabled.png)

Tape `ouvre Jarvis`, puis pose une question.

![Test](images/test.png)

La skill est aussi disponible automatiquement sur tes Echo liés au compte.

## Utilisation

```
"Alexa, ouvre Jarvis"
"je veux partir à Lisbonne combien ça va me coûter"
"et en avion ça met combien de temps"
"niveau langue ils parlent quoi"
"stop"
```

Pour effacer la mémoire en cours de session : `oublie tout`.

## Sécurité

- Restreins ta clé API à Gemini uniquement :
  [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
  → ta clé → API restrictions → Restrict key → Generative Language API.
  Obligatoire avant le 19 juin 2026 (Google désactive les clés non
  restreintes).
- Ne commit jamais ta clé. Le repo a `GEMINI_API_KEY = "YOUR_API_KEY"`,
  ta vraie clé reste chez Amazon.
- N'active pas Cloud Billing sur ton projet Google. Sans billing, aucune
  facturation possible.

## Coûts

Zéro. Le tier gratuit Gemini donne 1 500 requêtes/jour, Alexa-Hosted est
illimité gratuit pour les skills perso.

## Limites

- Le wake word reste `Alexa` (firmware verrouillé)
- La reconnaissance vocale reste celle d'Amazon
- Tes prompts peuvent être utilisés par Google pour entraîner ses modèles
  (tier gratuit uniquement)

## Personnaliser

- **Wake phrase** : `invocationName` dans [models/fr-FR.json](models/fr-FR.json),
  rebuild le modèle après
- **Personnalité** : `SYSTEM_INSTRUCTION` dans [lambda/lambda_function.py](lambda/lambda_function.py)
- **Modèle Gemini** : `GEMINI_MODEL` dans le même fichier (défaut :
  `gemini-2.5-flash-lite`)

## Dépannage

Jarvis te dit directement à l'oral ce qui cloche :

| Ce que dit Jarvis | Cause | Fix |
|---|---|---|
| « Limite de quota Gemini atteinte » | 1 500 req/jour dépassées | Attendre minuit (Pacifique) |
| « Problème d'authentification » | Clé invalide ou expirée | Régénérer la clé |
| « Le modèle Gemini configuré n'existe pas » | Modèle retiré par Google | Changer `GEMINI_MODEL` |
| « Le serveur Gemini ne répond pas » | Panne côté Google | Réessayer plus tard |
| « Problème de connexion réseau » | Lambda n'a pas pu joindre Google | Réessayer |
| « Gemini a mis trop de temps » | Timeout (8 s) | Réessayer |
| « Gemini n'a renvoyé aucune réponse » | Filtre de sécurité Google | Reformuler la question |
| « J'ai eu un souci » | Erreur inattendue | Voir CloudWatch Logs |

Pour les erreurs au démarrage de la Lambda (`ImportError urllib3` etc.),
voir les CloudWatch Logs depuis l'onglet Code de la console Alexa.

## Crédits

[k4l1sh/alexa-gpt](https://github.com/k4l1sh/alexa-gpt) (template d'origine,
MIT) · [Google Gemini](https://ai.google.dev/) · [Alexa Skills Kit](https://developer.amazon.com/alexa)

## Licence

[MIT](LICENSE)
