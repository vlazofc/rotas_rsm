# Tiles locais

O mapa do frontend usa Leaflet e procura tiles em:

`/tiles/{z}/{x}/{y}.png`

No Docker/Nginx, este diretório fica publicado em:

`/usr/share/nginx/html/tiles`

Coloque aqui tiles gerados por uma ferramenta própria, como `tilemaker`, `tileserver-gl`/export raster, ou outro processo interno baseado em dados OpenStreetMap. Evite baixar tiles em massa de servidores públicos.

Para desenvolvimento, pode apontar para outro servidor de tiles com:

`VITE_MAP_TILE_URL=https://seu-servidor/{z}/{x}/{y}.png`
