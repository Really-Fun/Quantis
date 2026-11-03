// Обложка трека: картинка из image://art/cover/…, пока грузится или если её
// нет — градиент от названия со значком ноты.
import QtQuick

Item {
    id: cover
    property string seed: ""
    property string cover: "" // url-encoded https (app.cover / роль cover)
    property real radius: theme.radiusSmall
    property real glyph: 0.4

    Rectangle {
        id: fallback
        anchors.fill: parent
        radius: cover.radius
        visible: image.status !== Image.Ready
        readonly property var colors: theme.coverColors(cover.seed)
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: fallback.colors[0] }
            GradientStop { position: 1; color: fallback.colors[1] }
        }
        Image {
            anchors.centerIn: parent
            width: parent.width * cover.glyph
            height: width
            source: "icons/music.svg"
            sourceSize: Qt.size(width, height)
            opacity: 0.55
            Accessible.ignored: true
        }
    }

    Image {
        id: image
        anchors.fill: parent
        asynchronous: true
        cache: true
        // Скругление в процентах стороны: провайдер рисует углы сам.
        readonly property int roundPct: width > 0 ? Math.round(cover.radius / width * 100) : 8
        source: cover.cover ? "image://art/cover/" + roundPct + "/" + cover.cover : ""
        sourceSize: Qt.size(Math.ceil(width), Math.ceil(height))
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: theme.medium } }
        Accessible.ignored: true
    }
}
