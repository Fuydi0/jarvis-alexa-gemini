"""
Skill Alexa custom — Gemini en français.

Adaptation du template k4l1sh/alexa-gpt :
- backend OpenAI -> Google Gemini (tier gratuit aistudio.google.com)
- réponses systématiquement en français, courtes, optimisées pour l'oral
- texte libre via ElicitSlotDirective : pas besoin de carrier phrases,
  Alexa attend explicitement le slot query et capture tout ce que dit
  l'utilisateur

Note : urllib3<2 est épinglé dans requirements.txt parce que le runtime
Python 3.8 d'Alexa-Hosted utilise OpenSSL 1.0.2k incompatible avec
urllib3 v2.
"""

import json
import logging

import requests
from ask_sdk_core.dispatch_components import (
    AbstractExceptionHandler,
    AbstractRequestHandler,
)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_intent_name, is_request_type
from ask_sdk_model import Response, Intent, Slot
from ask_sdk_model.dialog import ElicitSlotDirective

# Remplace YOUR_API_KEY par ta clé Gemini
GEMINI_API_KEY = "YOUR_API_KEY"

# Cascade de modèles : si le premier renvoie 429 (quota dépassé), on bascule
# automatiquement sur le suivant. Les quotas sont séparés par modèle dans
# le tier gratuit, donc cette cascade triple le quota effectif quotidien.
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",       # primaire — 1500 req/jour gratuites
    "gemini-flash-lite-latest",    # fallback 1 — alias, quota séparé
    "gemini-2.5-flash",            # fallback 2 — plus puissant, ~500/jour
]

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

SYSTEM_INSTRUCTION = (
    "Tu es un assistant vocal francophone branché sur une enceinte Alexa. "
    "Réponds toujours en français, en 60 mots maximum, en phrases courtes "
    "et naturelles à l'oral. Pas de listes à puces, pas de markdown, pas "
    "de titres. Si tu ne sais pas, dis-le simplement."
)

LAUNCH_MESSAGE = "Jarvis à ton écoute. Pose ta question."
EXIT_MESSAGE = "À la prochaine."
REPROMPT_MESSAGE = "Tu peux poser une autre question, ou dire stop pour arrêter."
CLEAR_MESSAGE = "Mémoire effacée. De quoi on parle ?"

# Messages d'erreur ciblés pour savoir d'un coup d'oreille ce qui cloche
ERROR_QUOTA = (
    "Limite de quota Gemini atteinte. Le quota gratuit se réinitialise "
    "à minuit, heure du Pacifique."
)
ERROR_AUTH = (
    "Problème d'authentification avec Gemini. La clé API est invalide ou "
    "expirée."
)
ERROR_MODEL_NOT_FOUND = (
    "Le modèle Gemini configuré n'existe pas. Il faut mettre à jour le "
    "nom du modèle dans le code."
)
ERROR_GEMINI_SERVER = (
    "Le serveur Gemini ne répond pas correctement. Réessaie dans quelques "
    "instants."
)
ERROR_NETWORK = (
    "Problème de connexion réseau. Réessaie dans quelques instants."
)
ERROR_TIMEOUT = (
    "Gemini a mis trop de temps à répondre. Réessaie."
)
ERROR_EMPTY_RESPONSE = (
    "Gemini n'a renvoyé aucune réponse. Reformule ta question."
)
ERROR_GENERIC = "Désolé, j'ai eu un souci. Tu peux reformuler ?"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _elicit_query_directive():
    """Directive qui dit à Alexa : remplis le slot 'query' de GptQueryIntent
    avec ce que l'utilisateur va dire ensuite (texte libre, peu importe la
    formulation)."""
    return ElicitSlotDirective(
        slot_to_elicit="query",
        updated_intent=Intent(
            name="GptQueryIntent",
            slots={"query": Slot(name="query")},
        ),
    )


def _build_gemini_payload(chat_history, new_question):
    contents = []
    for question, answer in chat_history:
        contents.append({"role": "user", "parts": [{"text": question}]})
        contents.append({"role": "model", "parts": [{"text": answer}]})
    contents.append({"role": "user", "parts": [{"text": new_question}]})

    return {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300},
    }


def _call_gemini_model(model, payload, headers):
    """Appelle un modèle Gemini précis. Renvoie un tuple (status, value) :
    - ('ok', texte)        → réponse réussie
    - ('quota', None)      → 429, à retenter avec un autre modèle
    - ('error', message)   → erreur définitive, ne pas retenter
    """
    url = GEMINI_URL_TEMPLATE.format(model=model)
    try:
        response = requests.post(
            url, headers=headers, data=json.dumps(payload), timeout=8
        )
    except requests.Timeout as exc:
        logger.error("Timeout Gemini (%s) : %s", model, exc)
        return ("error", ERROR_TIMEOUT)
    except requests.ConnectionError as exc:
        logger.error("Erreur de connexion Gemini (%s) : %s", model, exc)
        return ("error", ERROR_NETWORK)
    except requests.RequestException as exc:
        logger.error("Erreur réseau Gemini (%s) : %s", model, exc)
        return ("error", ERROR_NETWORK)

    if response.status_code == 429:
        logger.warning("Quota épuisé sur %s — fallback vers le modèle suivant", model)
        return ("quota", None)

    if not response.ok:
        logger.error("Gemini HTTP %s (%s) : %s", response.status_code, model, response.text)
        if response.status_code in (401, 403):
            return ("error", ERROR_AUTH)
        if response.status_code == 404:
            return ("error", ERROR_MODEL_NOT_FOUND)
        if response.status_code >= 500:
            return ("error", ERROR_GEMINI_SERVER)
        return ("error", ERROR_GENERIC)

    try:
        data = response.json()
    except ValueError as exc:
        logger.error("Réponse Gemini non-JSON (%s) : %s — corps: %s", model, exc, response.text)
        return ("error", ERROR_GENERIC)

    candidates = data.get("candidates") or []
    if not candidates:
        logger.error("Gemini n'a renvoyé aucun candidat (%s) — corps: %s", model, data)
        return ("error", ERROR_EMPTY_RESPONSE)

    try:
        return ("ok", candidates[0]["content"]["parts"][0]["text"].strip())
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Réponse Gemini inattendue (%s) : %s — corps: %s", model, exc, data)
        return ("error", ERROR_EMPTY_RESPONSE)


def generate_gemini_response(chat_history, new_question):
    """Tente la cascade de modèles définie dans GEMINI_MODELS. Si tous
    renvoient 429, retourne ERROR_QUOTA. Toute autre erreur stoppe la
    cascade immédiatement (pas la peine de retenter sur un autre modèle
    pour une clé invalide ou un problème réseau)."""
    if GEMINI_API_KEY in (None, "", "YOUR_API_KEY"):
        logger.error("GEMINI_API_KEY n'est pas configurée")
        return ERROR_AUTH

    payload = _build_gemini_payload(chat_history, new_question)
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    for model in GEMINI_MODELS:
        status, value = _call_gemini_model(model, payload, headers)
        if status == "ok":
            return value
        if status == "error":
            return value
        # status == "quota" → on continue la cascade

    logger.error("Tous les modèles Gemini ont renvoyé 429")
    return ERROR_QUOTA


class LaunchRequestHandler(AbstractRequestHandler):
    """Au lancement : ouvre la skill et demande explicitement le slot 'query'.

    L'ElicitSlotDirective force Alexa à capturer la prochaine phrase entière
    de l'utilisateur dans le slot, peu importe sa formulation, sans avoir
    besoin de carrier phrase comme « explique-moi » ou « pourquoi »."""

    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        handler_input.attributes_manager.session_attributes["chat_history"] = []
        return (
            handler_input.response_builder
            .speak(LAUNCH_MESSAGE)
            .ask(REPROMPT_MESSAGE)
            .add_directive(_elicit_query_directive())
            .response
        )


class GeminiQueryIntentHandler(AbstractRequestHandler):
    """Reçoit le slot 'query' rempli, appelle Gemini, puis réeéliciter le
    slot pour rester en mode conversation (la question suivante est captée
    sans nouveau lancement de skill)."""

    def can_handle(self, handler_input):
        return is_intent_name("GptQueryIntent")(handler_input)

    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots
        query_slot = slots.get("query") if slots else None
        query = query_slot.value if query_slot and query_slot.value else None

        # Cas où Alexa relance l'intent sans valeur de slot : on relance
        # l'élicitation au lieu de planter
        if not query:
            return (
                handler_input.response_builder
                .speak("Je n'ai rien capté. Tu peux reposer ta question ?")
                .ask(REPROMPT_MESSAGE)
                .add_directive(_elicit_query_directive())
                .response
            )

        session_attr = handler_input.attributes_manager.session_attributes
        chat_history = session_attr.setdefault("chat_history", [])

        recent_history = chat_history[-10:]
        response_text = generate_gemini_response(recent_history, query)

        chat_history.append((query, response_text))
        session_attr["chat_history"] = chat_history

        return (
            handler_input.response_builder
            .speak(response_text)
            .ask(REPROMPT_MESSAGE)
            .add_directive(_elicit_query_directive())
            .response
        )


class ClearContextIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("ClearContextIntent")(handler_input)

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes
        session_attr["chat_history"] = []
        return (
            handler_input.response_builder
            .speak(CLEAR_MESSAGE)
            .ask(REPROMPT_MESSAGE)
            .add_directive(_elicit_query_directive())
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (
            is_intent_name("AMAZON.CancelIntent")(handler_input)
            or is_intent_name("AMAZON.StopIntent")(handler_input)
        )

    def handle(self, handler_input):
        return handler_input.response_builder.speak(EXIT_MESSAGE).response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = (
            "Pose-moi n'importe quelle question. "
            "Dis efface la mémoire pour repartir de zéro, "
            "ou stop pour arrêter."
        )
        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask(REPROMPT_MESSAGE)
            .add_directive(_elicit_query_directive())
            .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(exception, exc_info=True)
        return (
            handler_input.response_builder
            .speak(ERROR_GENERIC)
            .ask(REPROMPT_MESSAGE)
            .add_directive(_elicit_query_directive())
            .response
        )


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(GeminiQueryIntentHandler())
sb.add_request_handler(ClearContextIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
