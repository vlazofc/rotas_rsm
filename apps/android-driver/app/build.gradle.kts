plugins { id("com.android.application") }

val driverAppUrl = providers.gradleProperty("DRIVER_APP_URL").orElse("https://adimax.jmtransportes.tech").get()
providers.gradleProperty("ANDROID_BUILD_DIR").orNull?.let { layout.buildDirectory.set(file(it)) }

android {
    namespace = "br.com.adimax.rotas.motorista"
    compileSdk = 35
    defaultConfig {
        applicationId = "br.com.adimax.rotas.motorista"
        minSdk = 26
        targetSdk = 35
        versionCode = 13
        versionName = "1.3.0"
        buildConfigField("String", "APP_URL", "\"${driverAppUrl.replace("\"", "\\\"")}\"")
        buildConfigField("String", "UPDATE_URL", "\"${driverAppUrl.replace("\"", "\\\"")}/downloads/adimax-motorista-version.json\"")
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core:1.15.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    constraints { implementation("org.jetbrains.kotlin:kotlin-stdlib:1.8.22") }
}

configurations.configureEach {
    exclude(group = "org.jetbrains.kotlin", module = "kotlin-stdlib-jdk7")
    exclude(group = "org.jetbrains.kotlin", module = "kotlin-stdlib-jdk8")
}
