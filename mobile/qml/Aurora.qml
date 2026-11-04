// Аврора из цветов обложки: три мягких пятна медленно плывут. Пока играет —
// «дышит», на паузе затихает; energy > 1 — вспышка (скретч пластинки).
import QtQuick

Item {
    id: aurora
    property bool active: false
    property real energy: active ? 1 : 0.35
    property real flash: 1
    // Плавный вход сверху (px): аврора растворяется в тёмной строке
    // состояния, а не обрывается о неё.
    property real topFade: 0
    // Внизу — до сплошного фона: на главной аврора кончается посреди
    // страницы, и без этого был виден её край.
    property bool fadeOut: false
    clip: true
    Behavior on energy { NumberAnimation { duration: 1200; easing.type: Easing.InOutQuad } }
    Behavior on flash { NumberAnimation { duration: 260 } }

    function hex(color) {
        function part(v) { var h = Math.round(v * 255).toString(16); return h.length < 2 ? "0" + h : h }
        return part(color.r) + part(color.g) + part(color.b)
    }

    Repeater {
        model: [
            { color: "glow", x: 0.05, y: 0.02, size: 1.25, period: 14000 },
            { color: "accent2", x: 0.55, y: 0.18, size: 1.05, period: 17000 },
            { color: "deep", x: 0.15, y: 0.52, size: 1.4, period: 21000 }
        ]
        delegate: Image {
            id: blob
            required property var modelData
            required property int index
            readonly property real base: Math.max(aurora.width, aurora.height) * modelData.size
            width: base
            height: base
            x: aurora.width * modelData.x - base / 2 + drift * aurora.width * 0.12
            y: aurora.height * modelData.y - base / 4 + drift * aurora.height * 0.06
            property real drift: 0
            source: "image://art/blob/" + aurora.hex(modelData.color === "glow" ? theme.glow
                                                    : modelData.color === "accent2" ? theme.accent2
                                                    : Qt.lighter(theme.deep, 2.4))
            sourceSize: Qt.size(256, 256)
            smooth: true
            opacity: Math.min(1, aurora.energy * aurora.flash)
            scale: 1 + (breath - 0.5) * 0.08 * aurora.energy
            property real breath: 0.5
            Accessible.ignored: true

            SequentialAnimation on drift {
                running: theme.motion && aurora.visible
                loops: Animation.Infinite
                NumberAnimation { from: -1; to: 1; duration: blob.modelData.period; easing.type: Easing.InOutSine }
                NumberAnimation { from: 1; to: -1; duration: blob.modelData.period; easing.type: Easing.InOutSine }
            }
            SequentialAnimation on breath {
                running: theme.motion && aurora.active && aurora.visible
                loops: Animation.Infinite
                NumberAnimation { to: 1; duration: 2200 + blob.index * 500; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0; duration: 2200 + blob.index * 500; easing.type: Easing.InOutSine }
            }
        }
    }

    // Затемнение снизу: текст и кнопки поверх авроры остаются читаемыми.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(0.043, 0.051, 0.071, 0.05) }
            GradientStop { position: 0.55; color: Qt.rgba(0.043, 0.051, 0.071, 0.3) }
            GradientStop { position: 1; color: Qt.rgba(0.043, 0.051, 0.071, aurora.fadeOut ? 1 : 0.88) }
        }
    }
    Rectangle {
        visible: aurora.topFade > 0
        width: parent.width
        height: aurora.topFade
        gradient: Gradient {
            GradientStop { position: 0; color: theme.bg }
            GradientStop { position: 1; color: Qt.rgba(0.043, 0.051, 0.071, 0) }
        }
    }
}
