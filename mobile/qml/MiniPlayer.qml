// Мини-плеер над нижней панелью: касание или свайп вверх открывают плеер.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ItemDelegate {
    id: mini
    signal open()

    height: theme.miniHeight
    padding: 0
    leftPadding: 8
    rightPadding: 4
    Accessible.name: "Открыть плеер: " + app.title
    onClicked: mini.open()

    background: Rectangle {
        radius: theme.radius
        color: mini.down ? theme.surfaceHigh : theme.surface
        border.color: theme.stroke
        Behavior on color { ColorAnimation { duration: theme.fast } }

        // Тонкая полоса прогресса по нижнему краю карточки.
        Rectangle {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.leftMargin: theme.radius / 2
            anchors.bottomMargin: 1
            height: 2
            radius: 1
            width: (parent.width - theme.radius) * (app.duration > 0 ? app.position / app.duration : 0)
            color: theme.accent
        }
    }

    contentItem: RowLayout {
        spacing: 12
        CoverArt {
            Layout.preferredWidth: 48
            Layout.preferredHeight: 48
            seed: app.title
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text {
                Layout.fillWidth: true
                text: app.title
                color: theme.text
                font.family: theme.ui
                font.pixelSize: 15
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: app.loading ? "Загружаем…" : app.artist
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 13
                elide: Text.ElideRight
            }
        }
        IconButton {
            iconName: app.playing ? "pause" : "play"
            label: app.playing ? "Пауза" : "Играть"
            onClicked: app.toggle()
        }
        IconButton {
            iconName: "skip-forward"
            label: "Следующий трек"
            iconSize: 22
            onClicked: app.next()
        }
    }

    // Свайп вверх по мини-плееру — открыть плеер (кнопка-касание дублирует).
    DragHandler {
        target: null
        yAxis.enabled: true
        xAxis.enabled: false
        onActiveChanged: if (!active && centroid.position.y - centroid.pressPosition.y < -24) mini.open()
    }
}
