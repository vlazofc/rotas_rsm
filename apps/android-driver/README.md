# Adimax Motorista — Android

Aplicativo Android nativo que abre o portal Adimax com o mesmo login e as permissões do perfil `motorista`. Inclui câmera/arquivos para comprovantes e a ponte `AndroidLocation` usada pelo compartilhamento GPS.

## Abrir e executar

1. No Android Studio, escolha **Open** e selecione `apps/android-driver`.
2. Aguarde a sincronização do SDK 35 e do Gradle (JDK 17).
3. Selecione um aparelho ou emulador e clique em **Run**.

Por padrão abre `https://adimax.jmtransportes.tech`. Para usar o Docker local no emulador, altere `gradle.properties` para:

```properties
DRIVER_APP_URL=http://10.0.2.2:8089
```

## Gerar APK

- Teste: **Build > Build APK(s)**.
- Produção: **Build > Generate Signed Bundle / APK > APK**, escolha a chave e a variante `release`.
- Saída de teste: `app/build/outputs/apk/debug/app-debug.apk`.

Login, sessão e permissões continuam validados pela API. O usuário precisa estar ativo, ter perfil `motorista` e estar vinculado ao cadastro escalado na rota.

## Atualizações

Ao abrir, o aplicativo consulta `/downloads/adimax-motorista-version.json`. Quando o `versionCode` publicado for maior, oferece o download e abre a instalação da nova versão. O Android exige que o usuário confirme a instalação e, na primeira atualização, autorize esta fonte. Telas e regras carregadas do servidor são atualizadas sem reinstalar o APK.

## Trocar o ícone

Substitua `app/src/main/res/drawable/adimax_icon.png` por uma imagem PNG quadrada, de preferência com fundo transparente e resolução de 512×512 ou 1024×1024. Mantenha o mesmo nome e gere novamente o APK. O fundo amarelo e o recorte adaptativo são aplicados pelo próprio projeto.
