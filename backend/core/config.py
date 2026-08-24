from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Basic Project Info
    PROJECT_NAME: str = "PrivaCheck GDPR Crawler"
    VERSION: str = "0.1.0"

    # Crawler Settings (We will use these later when we build the crawler)
    CRAWLER_TIMEOUT_SECONDS: int = 30
    CRAWLER_HEADLESS: bool = True
    
    # API Settings
    API_V1_STR: str = "/api/v1"

    # This tells Pydantic to read from a .env file if it exists
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# We create a single instance of this class that the rest of our app can import and use
settings = Settings()
