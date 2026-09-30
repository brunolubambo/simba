import asyncio
from dotenv import load_dotenv
load_dotenv()
from .core import Simba


async def approve(prompt: str) -> bool:
    ans = await asyncio.to_thread(input, f"\n[aprovação] {prompt}\nPermitir? (s/N) ")
    return ans.strip().lower() in ("s", "sim", "y", "yes")


async def main():
    simba = Simba(approve)
    print("SIMBA online. Digite 'sair' para encerrar.\n")
    try:
        while True:
            text = (await asyncio.to_thread(input, "você> ")).strip()
            if text.lower() in ("sair", "exit"):
                break
            if not text:
                continue
            async for ev in simba.ask(text):
                if ev["type"] == "text":
                    print(f"\nsimba> {ev['text']}")
                elif ev["type"] == "tool":
                    print(f"  · {ev['name']}")
                elif ev["type"] == "done" and ev.get("cost_usd"):
                    print(f"  (custo equivalente: US$ {ev['cost_usd']:.4f})")
    finally:
        await simba.stop()


if __name__ == "__main__":
    asyncio.run(main())
