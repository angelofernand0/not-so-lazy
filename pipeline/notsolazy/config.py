"""Environment configuration. Offline commands do not require an SEC identity."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    sec_user_agent: str = ""
    sec_requests_per_second: float = Field(default=8, gt=0, le=8)
    database_url: SecretStr = SecretStr("sqlite:///./data/notsolazy.db")
    blob_backend: Literal["local", "r2"] = "local"
    data_dir: Path = Path("./data")
    section_item: str = "1A"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = ""
    r2_endpoint_url: str = ""
    r2_bucket: str = ""
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None

    def require_sec_identity(self) -> str:
        identity = self.sec_user_agent.strip()
        if not re.search(r"\S+@\S+\.\S+", identity):
            raise ValueError("Set SEC_USER_AGENT to 'NotSoLazy/0.1 your-contact@example.com'.")
        return identity

    @property
    def summaries_enabled(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value().strip())


@dataclass(frozen=True)
class SectionRule:
    item: str
    title: str
    next_headers: tuple[tuple[str, str], ...]
    primary_key: str
    min_words: int = 2000
    bare_end_titles: tuple[str, ...] = ()


SECTION_RULES = {
    "1A": SectionRule(
        "1A",
        "Risk Factors",
        (("1B", "Unresolved Staff Comments"), ("1C", "Cybersecurity"), ("2", "Properties")),
        "risk_factors",
        bare_end_titles=(
            "Quantitative and Qualitative Disclosures about Market Risks",
            "Quantitative and Qualitative Disclosures About Market Risk",
            "Other Key Information",
            "Unresolved Staff Comments",
            "Cybersecurity",
            "Properties",
            "Legal Proceedings",
        ),
    ),
}


def section_rule(item: str) -> SectionRule:
    try:
        return SECTION_RULES[item.upper()]
    except KeyError:
        raise ValueError(f"Section {item} is not supported yet.") from None
