// Строка трека: обложка, название, исполнитель · длина, источник. Касание —
// играть; играющая строка подсвечена акцентом.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ItemDelegate {
    id: row
    // Роли модели — required: делегат ListView получает их по имени.
    required property int index
    required property string title
    required property string artist
    required property int duration
    required property string source
    property bool current: false

    width: ListView.view ? ListView.view.width : implicitWidth
    height: 72
    padding: 0
    leftPadding: theme.gutter
    rightPadding: theme.gutter
    Accessible.name: title + ", " + artist

    contentItem: RowLayout {
        spacing: 12
        CoverArt {
            Layout.preferredWidth: 48
            Layout.preferredHeight: 48
            seed: row.title
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: row.title
                color: row.current ? theme.accent : theme.text
                font.family: theme.ui
                font.pixelSize: 16
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            RowLayout {
                spacing: 6
                Layout.fillWidth: true
                SourceBadge { source: row.source }
                Text {
                    Layout.fillWidth: true
                    text: row.artist + (row.duration > 0 ? "  ·  " + theme.formatTime(row.duration * 1000) : "")
                    color: theme.textDim
                    font.family: theme.ui
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
        }
    }
}
