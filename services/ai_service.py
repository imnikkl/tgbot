import logging
import google.generativeai as genai

LOGGER = logging.getLogger(__name__)

class AiService:
    def __init__(self, api_key: str | None):
        self._is_configured = False
        self.model = None
        
        if not api_key:
            return

        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-1.5-flash-latest")
            self._is_configured = True
            LOGGER.info("AI Service a fost configurat cu succes.")
        except Exception as exc:
            LOGGER.error("Eroare la configurarea AI Service", extra={"error": str(exc)})

    @property
    def is_configured(self) -> bool:
        return self._is_configured

    async def get_intelligent_response(self, question: str, weather_context: str) -> str:
        if not self._is_configured or not self.model:
            return "Ne pare rău, dar funcția AI nu este configurată (lipsă cheie API Gemini)."

        prompt = (
            f"Ești un asistent inteligent într-un bot de Telegram dedicat vremii. "
            f"Răspunde prietenos și concis la următoarea întrebare a utilizatorului.\n\n"
            f"Contextul meteo curent și pentru zilele următoare pentru locația utilizatorului:\n"
            f"{weather_context}\n\n"
            f"Întrebarea utilizatorului:\n{question}\n\n"
            f"Te rog să oferi un răspuns clar bazat pe starea vremii (dacă e relevant pentru întrebare). "
            f"Nu include informații de prisos, răspunde direct la obiect pe un ton util și uman. "
            f"Folosește formatare HTML simplă (<b>, <i>) dacă e nevoie. Nu răspunde la întrebări care "
            f"nu au legătură sau nu pot fi deduse, dar fii flexibil."
        )

        try:
            response = await self.model.generate_content_async(prompt)
            return response.text
        except Exception as exc:
            LOGGER.error("Generarea răspunsului AI a eșuat", extra={"error": str(exc)})
            return "Îmi pare rău, dar am întâmpinat o eroare la generarea răspunsului AI."
