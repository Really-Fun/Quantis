// Обложка трека. Шаг 1 — градиент и значок; настоящие обложки — шаг 2.
import QtQuick

Rectangle {
    id: cover
    property string seed: ""
    property real glyph: 0.4

    radius: theme.radiusSmall
    readonly property var colors: theme.coverColors(seed)
    gradient: Gradient {
        orientation: Gradient.Vertical
        GradientStop { position: 0; color: cover.colors[0] }
        GradientStop { position: 1; color: cover.colors[1] }
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
