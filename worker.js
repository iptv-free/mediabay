export default {
  async fetch(request, env, ctx) {
    const apiUrl = "https://api.mediabay.uz/v2/channels/listRadio";
    
    const headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9,uz;q=0.8",
      "Referer": "https://mediabay.uz/"
    };

    try {
      const response = await fetch(apiUrl, { headers });
      
      if (!response.ok) {
        return new Response(`Mediabay API blokladi: ${response.status}`, { status: response.status });
      }

      const result = await response.json();

      if (result.status !== "ok") {
        return new Response("API dan noto'g'ri format keldi", { status: 502 });
      }

      const channels = result.data || [];
      const mediaHost = result.mediaHost || "https://media.mediabay.uz";

      let m3uLines = ["#EXTM3U"];

      channels.forEach(ch => {
        const name = ch.name || "Radio";
        const logo = ch.logo ? String(ch.logo) : "";
        const logoUrl = logo.startsWith("/") ? `${mediaHost}${logo}` : logo;
        const previewUrl = ch.preview || "";

        m3uLines.push(`#EXTINF:-1 tvg-logo="${logoUrl}",${name}`);
        m3uLines.push(previewUrl);
      });

      const playlistContent = m3uLines.join("\n");

      return new Response(playlistContent, {
        headers: {
          "Content-Type": "audio/x-mpegurl; charset=utf-8",
          "Access-Control-Allow-Origin": "*",
          "Cache-Control": "no-cache"
        }
      });

    } catch (err) {
      return new Response(`Server xatosi: ${err.message}`, { status: 500 });
    }
  }
};
