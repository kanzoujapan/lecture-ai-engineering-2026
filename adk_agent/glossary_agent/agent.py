"""第3回 発展(a): 同じ指示文・ツールをGoogle ADKで組み立てる。"""

from google.adk.agents import Agent

from app import tools
from app.agent import INSTRUCTIONS
from app.config import MODEL

root_agent = Agent(
    name="glossary_agent",
    model=MODEL,
    instruction=INSTRUCTIONS,
    tools=[tools.search_glossary, tools.get_lecture_summary, tools.make_quiz],
)
