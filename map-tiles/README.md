# Tiles de mapa locais

O frontend procura tiles raster em:

`/tiles/{z}/{x}/{y}.png`

No Docker Compose, este diretório é montado no container web:

`./map-tiles -> /usr/share/nginx/html/tiles`

Estrutura esperada:

```text
map-tiles/
  6/
    30/
      23.png
    ...
```

Este diretório já contém tiles reais do OpenStreetMap para Portugal continental, Atlântico próximo e oeste de Espanha nos zooms 6 a 9. O Leaflet usa `maxNativeZoom: 9`, então zooms acima disso escalam os tiles locais.

Use tiles gerados internamente a partir de dados OpenStreetMap ou outro provedor com licença compatível. Não use Google Maps baixado/cacheado nem download em massa de tiles públicos.
