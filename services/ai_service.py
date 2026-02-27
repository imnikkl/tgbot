import logging
from google import genai

LOGGER = logging.getLogger(__name__)

class AiService:
    def __init__(self, api_key: str | None):
        self._is_configured = False
        self.client = None
        
        if not api_key:
            return

        try:
            self.client = genai.Client(api_key=api_key)
            self._is_configured = True
            LOGGER.info("AI Service a fost configurat cu succes.")
        except Exception as exc:
            LOGGER.error("Eroare la configurarea AI Service", extra={"error": str(exc)})

    @property
    def is_configured(self) -> bool:
        return self._is_configured

    async def get_intelligent_response(self, question: str, weather_context: str) -> str:
        if not self._is_configured or not self.client:
            return "Ne pare rău, dar funcția AI nu este configurată (lipsă cheie API Gemini)."

        prompt = (
            f"Ești un asistent inteligent într-un bot de Telegram dedicat vremii. "
            f"Nu folosi absolut deloc formule de salut (de ex: Salut, Bună, etc) la începutul răspunsului. "
            f"Răspunde prietenos și concis, direct la subiect, ca o continuare a conversației cu utilizatorul.\n\n"
            f"Contextul meteo curent și pentru zilele următoare pentru locația utilizatorului:\n"
            f"{weather_context}\n\n"
            f"Întrebarea utilizatorului:\n{question}\n\n"
            f"Oferă un răspuns clar bazat pe starea vremii (dacă e relevant pentru întrebare). "
            f"Folosește formatare HTML simplă (<b>, <i>) pentru a evidenția, dar nu exagera. Fii flexibil, dar "
            f"refuză elegant întrebările complet paralele cu vremea sau utilitățile ei."
        )

        try:
            # We use the new genai Client directly. Note: The new generate_content is synchronous but thread blocking might be low for short prompts. Or we use generate_content_async if available, but let's stick to standard.
            # actually genai.Client provides async methods via client.aio
            response = await self.client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text
        except Exception as exc:
            LOGGER.error("Generarea răspunsului AI a eșuat", extra={"error": str(exc)})
            return "Îmi pare rău, dar am întâmpinat o eroare la generarea răspunsului AI."
