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
    required property string cover
    required property bool offline // скачан на телефон
    property bool current: false
    property string listName: "results" // какой список (для меню и касания)
    onClicked: app.playFrom(listName, index)

    width: ListView.view ? ListView.view.width : implicitWidth
    height: 72
    padding: 0
    leftPadding: theme.gutter
    rightPadding: 4
    Accessible.name: title + ", " + artist

    contentItem: RowLayout {
        spacing: 12
        CoverArt {
            Layout.preferredWidth: 48
            Layout.preferredHeight: 48
            seed: row.title
            cover: row.cover
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
                Image {
                    visible: row.offline
                    source: "icons/downloaded.svg"
                    sourceSize: Qt.size(14, 14)
                    Layout.preferredWidth: 14; Layout.preferredHeight: 14
                    Accessible.name: "Скачан"
                }
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
        IconButton {
            iconName: "more-vertical"
            label: "Действия с треком"
            tint: theme.textDim
            onClicked: menu.popup(this, 0, height)
        }
    }

    TrackMenu {
        id: menu
        listName: row.listName
        trackIndex: row.index
    }
}
