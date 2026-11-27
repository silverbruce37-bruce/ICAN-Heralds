import asyncio
from playwright.async_api import async_playwright

URL = "https://ican-heralds.vercel.app/?v=ca565ac"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        for name, korean in [("vocab-algorithm-light", True), ("vocab-algorithm-light-en", False)]:
            pg = await b.new_page(viewport={"width": 1400, "height": 2200}, device_scale_factor=2)
            await pg.goto(URL, wait_until="load")
            await pg.wait_for_timeout(1500)
            if korean:
                await pg.click("#langBtn")
                await pg.wait_for_timeout(500)
            await pg.evaluate("document.querySelector('.word-alg').scrollIntoView({block:'center'})")
            await pg.wait_for_timeout(1500)
            info = await pg.evaluate("""() => {
                const b = document.querySelector('.word-banner').getBoundingClientRect();
                const a = document.querySelector('.word-alg').getBoundingClientRect();
                const btn = document.getElementById('langBtn');
                return {b: {y: b.y + window.scrollY, h: b.height, x: b.x, w: b.width},
                        a: {y: a.y + window.scrollY, h: a.height, x: a.x, w: a.width},
                        op: getComputedStyle(document.querySelector('.word-banner')).opacity,
                        lang: btn ? btn.textContent.trim() : null};
            }""")
            b1, b2 = info["b"], info["a"]
            clip = {
                "x": max(min(b1["x"], b2["x"]) - 16, 0),
                "y": b1["y"] - 16,
                "width": max(b1["w"], b2["w"]) + 32,
                "height": (b2["y"] + b2["h"]) - b1["y"] + 32,
            }
            await pg.screenshot(path=f"/workspace/downloads/heralds-2026-11-27/{name}.png", clip=clip, full_page=True)
            print(name, "banner opacity", info["op"], "lang btn", info["lang"], clip)
            await pg.close()
        await b.close()


asyncio.run(main())
