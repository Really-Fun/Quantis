// Большая круглая кнопка «Играть/Пауза» цветом акцента, как в настольном
// Quantis; пока трек грузится — кольцо загрузки вокруг.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material

AbstractButton {
    id: control
    property int size: 72

    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.Button
    Accessible.name: app.playing ? "Пауза" : "Играть"
    onClicked: app.toggle()

    background: Rectangle {
        radius: width / 2
        color: theme.accent
        scale: control.down ? 0.94 : 1
        Behavior on scale { NumberAnimation { duration: theme.fast } }
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "#FFFFFF"
            opacity: control.down ? 0.16 : 0
            Behavior on opacity { NumberAnimation { duration: theme.fast } }
        }
    }
    contentItem: Item {
        Image {
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: app.playing ? 0 : 2 // треугольник визуально по центру
            width: control.size * 0.4
            height: width
            source: app.playing ? "icons/pause.svg" : "icons/play.svg"
            sourceSize: Qt.size(width, height)
            Accessible.ignored: true
        }
    }
    BusyIndicator {
        anchors.centerIn: parent
        width: control.size + 14
        height: width
        running: app.loading
        visible: running
        Material.accent: theme.accentCyan
    }
}
