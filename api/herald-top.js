const FEEDS = [
    'https://www.koreaherald.com/rss/kh_World',
    'https://stg-www.koreaherald.com/rss/kh_World'
];

function decodeEntities(value = '') {
    return value
        .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&apos;/g, "'")
        .replace(/&#39;/g, "'")
        .trim();
}

function tagValue(item, tag) {
    const match = item.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'));
    return decodeEntities(match ? match[1] : '');
}

function tagAttribute(item, tag, attr) {
    const match = item.match(new RegExp(`<${tag}[^>]*\\s${attr}=["']([^"']+)["'][^>]*>`, 'i'));
    return decodeEntities(match ? match[1] : '');
}

function parseFirstItem(xml) {
    const itemMatch = xml.match(/<item\b[^>]*>([\s\S]*?)<\/item>/i);
    if (!itemMatch) return null;

    const item = itemMatch[1];
    const title = tagValue(item, 'title');
    const rawLink = tagValue(item, 'link');
    const link = rawLink.startsWith('http') ? rawLink : `https://www.koreaherald.com${rawLink}`;
    const publishedAt = tagValue(item, 'pubDate');
    const description = tagValue(item, 'description').replace(/<[^>]+>/g, '').trim();
    const imageUrl = tagAttribute(item, 'media:content', 'url');

    if (!title || !link) return null;

    return {
        source: 'The Korea Herald',
        section: 'World',
        title,
        link,
        publishedAt,
        description,
        imageUrl
    };
}

module.exports = async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 's-maxage=1800, stale-while-revalidate=21600');

    for (const feed of FEEDS) {
        try {
            const response = await fetch(feed, {
                headers: {
                    'user-agent': 'ICAN-Heralds/1.0 (+https://ican-heralds.vercel.app/)'
                }
            });
            if (!response.ok) continue;

            const xml = await response.text();
            const story = parseFirstItem(xml);
            if (story) {
                return res.status(200).json(story);
            }
        } catch (error) {
            // Try the next known Korea Herald host.
        }
    }

    return res.status(502).json({
        error: 'Unable to load The Korea Herald World RSS feed'
    });
};
