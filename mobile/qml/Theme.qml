// Токены дизайна: палитра Aurora настольного Quantis, шрифты Unbounded
// (заголовки) и Manrope (интерфейс), сетка 4/8 dp. Экраны берут цвета
// и размеры только отсюда.
import QtQuick

Item {
    visible: false

    // Цвета (тёмная тема OLED). Контраст текста на bg: text 17:1, textDim 6:1.
    readonly property color bg: "#0B0D12"
    readonly property color surface: "#151922"
    readonly property color surfaceHigh: "#1D2230"
    readonly property color stroke: "#262C3B"
    readonly property color text: "#F2F4F8"
    readonly property color textDim: "#9AA2B5"
    // Цвета из обложки играющего трека (backend: art.palette_from) с
    // плавным переходом, как в настольном Quantis (~0,9 с).
    property color accent: app.accent
    property color accent2: app.accent2
    property color glow: app.glow
    property color deep: app.deep
    property color accentText: app.accentText
    Behavior on accent { ColorAnimation { duration: 900 } }
    Behavior on accent2 { ColorAnimation { duration: 900 } }
    Behavior on glow { ColorAnimation { duration: 900 } }
    Behavior on deep { ColorAnimation { duration: 900 } }
    readonly property color accentPink: "#FF2A7F"
    readonly property color accentCyan: "#00D8F0"

    // Движение: системные анимации включены и приложение на экране.
    readonly property bool motion: app.animations && Qt.application.state === Qt.ApplicationActive
    readonly property color yandex: "#FFCC00"
    readonly property color youtube: "#FF3B30"
    readonly property color danger: "#FF6B6B"

    // Размеры.
    readonly property int gutter: 16
    readonly property int radius: 16
    readonly property int radiusSmall: 10
    readonly property int touch: 48 // минимум для касания на Android
    readonly property int navHeight: 64
    readonly property int miniHeight: 64

    // Время анимаций: короткое для отклика, среднее для переходов.
    readonly property int fast: 120
    readonly property int medium: 240

    readonly property string display: unbounded.name
    readonly property string ui: manrope.name

    FontLoader { id: manrope; source: "fonts/Manrope-Regular.ttf" }
    FontLoader { source: "fonts/Manrope-Medium.ttf" }
    FontLoader { source: "fonts/Manrope-SemiBold.ttf" }
    FontLoader { source: "fonts/Manrope-Bold.ttf" }
    FontLoader { id: unbounded; source: "fonts/Unbounded-SemiBold.ttf" }
    FontLoader { source: "fonts/Unbounded-Bold.ttf" }

    function formatTime(ms) {
        var total = Math.max(0, Math.floor(ms / 1000))
        var seconds = total % 60
        return Math.floor(total / 60) + ":" + (seconds < 10 ? "0" : "") + seconds
    }

    // Запасной градиент, пока обложка грузится или если её нет.
    function coverColors(seed) {
        var hash = 0
        for (var i = 0; i < seed.length; i++)
            hash = (hash * 31 + seed.charCodeAt(i)) & 0xffffff
        var hue = (hash % 360) / 360
        return [Qt.hsla(hue, 0.55, 0.42, 1), Qt.hsla((hue + 0.12) % 1, 0.65, 0.22, 1)]
    }
}
