// Пластинка с обложкой на «яблоке». Крутится, пока играет (плавный разгон
// и остановка). По пластинке можно водить пальцем как диджей: вращение
// перематывает трек, сигнал scratching — для вспышки авроры.
import QtQuick

Item {
    id: vinyl
    property string cover: ""
    property bool spinning: false
    property bool scratchable: false
    property real degreesPerSecond: 120 // спокойнее, чем 33⅓ об/мин
    property real msPerTurn: 4000 // скретч: оборот — 4 секунды трека
    property real exposedFromX: 0 // левее — под обложкой: касание не наше
    readonly property bool scratching: scratch.pressed

    // Скорость плавно уходит в 0 и обратно — пластинка «тормозит», а не замирает.
    property real speed: spinning && theme.motion ? 1 : 0
    Behavior on speed { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }

    Image {
        id: disc
        anchors.fill: parent
        asynchronous: true
        source: "image://art/vinyl/" + vinyl.cover
        sourceSize: Qt.size(Math.ceil(width), Math.ceil(height))
        smooth: true
        Accessible.ignored: true
    }

    FrameAnimation {
        running: vinyl.speed > 0 && !scratch.pressed
        onTriggered: disc.rotation = (disc.rotation + vinyl.speed * vinyl.degreesPerSecond * frameTime) % 360
    }

    MouseArea {
        id: scratch
        anchors.fill: parent
        enabled: vinyl.scratchable && app.duration > 0
        property real lastAngle: 0
        property real previewMs: 0
        preventStealing: true

        function angleAt(x, y) {
            return Math.atan2(y - height / 2, x - width / 2) * 180 / Math.PI
        }
        onPressed: function (mouse) {
            if (mouse.x < vinyl.exposedFromX) {
                mouse.accepted = false
                return
            }
            lastAngle = angleAt(mouse.x, mouse.y)
            previewMs = app.position
        }
        onPositionChanged: function (mouse) {
            var angle = angleAt(mouse.x, mouse.y)
            var delta = angle - lastAngle
            if (delta > 180) delta -= 360
            if (delta < -180) delta += 360
            lastAngle = angle
            disc.rotation = (disc.rotation + delta) % 360
            previewMs = Math.max(0, Math.min(app.duration, previewMs + delta / 360 * vinyl.msPerTurn))
        }
        onReleased: app.seek(previewMs)
    }
    Accessible.role: Accessible.Slider
    Accessible.name: "Пластинка: поверни, чтобы перемотать"
}
