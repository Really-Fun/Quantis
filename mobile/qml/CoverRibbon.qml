// Лента обложек с заголовком: альбомы, плейлисты, исполнители (круглые).
// Элемент модели — объект {title|name, subtitle, cover (https), icon?}.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ColumnLayout {
    id: ribbon
    property string title
    property var model: []
    property bool round: false
    property int tile: 140
    property bool showAll: false
    signal picked(var item, int index)
    signal allClicked()

    Layout.fillWidth: true
    visible: model && model.length > 0
    spacing: 12

    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: theme.gutter
        Layout.rightMargin: theme.gutter - 8
        Text {
            Layout.fillWidth: true
            text: ribbon.title
            color: theme.text
            font.family: theme.display
            font.pixelSize: 18
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        PillButton {
            visible: ribbon.showAll
            text: "Все"
            variant: "text"
            compact: true
            onClicked: ribbon.allClicked()
        }
    }
    ListView {
        Layout.fillWidth: true
        Layout.preferredHeight: ribbon.tile + 64
        orientation: ListView.Horizontal
        spacing: 12
        leftMargin: theme.gutter
        rightMargin: theme.gutter
        clip: true
        boundsBehavior: Flickable.DragOverBounds
        model: ribbon.model
        delegate: ItemDelegate {
            id: cell
            required property var modelData
            required property int index
            readonly property string label: modelData.title || modelData.name || ""
            width: ribbon.tile
            height: ribbon.tile + 64
            padding: 0
            Accessible.name: label + (modelData.subtitle ? ", " + modelData.subtitle : "")
            onClicked: ribbon.picked(modelData, index)
            background: Item {}
            contentItem: ColumnLayout {
                spacing: 8
                Item {
                    Layout.preferredWidth: ribbon.tile
                    Layout.preferredHeight: ribbon.tile
                    scale: cell.down ? 0.97 : 1
                    Behavior on scale { NumberAnimation { duration: theme.fast } }
                    CoverArt {
                        anchors.fill: parent
                        visible: !cell.modelData.icon
                        radius: ribbon.round ? width / 2 : 14
                        seed: cell.label
                        cover: cell.modelData.cover ? encodeURIComponent(cell.modelData.cover) : ""
                    }
                    Rectangle { // плитка-значок («Мне нравится», «Новый плейлист»)
                        anchors.fill: parent
                        visible: !!cell.modelData.icon
                        radius: 14
                        gradient: Gradient {
                            GradientStop { position: 0; color: theme.accent }
                            GradientStop { position: 1; color: theme.accentPink }
                        }
                        Image {
                            anchors.centerIn: parent
                            source: cell.modelData.icon ? "icons/" + cell.modelData.icon + ".svg" : ""
                            sourceSize: Qt.size(ribbon.tile * 0.34, ribbon.tile * 0.34)
                            Accessible.ignored: true
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: ribbon.round ? Text.AlignHCenter : Text.AlignLeft
                    text: cell.label
                    color: theme.text
                    font.family: theme.ui
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!cell.modelData.subtitle
                    horizontalAlignment: ribbon.round ? Text.AlignHCenter : Text.AlignLeft
                    text: cell.modelData.subtitle || ""
                    color: theme.textDim
                    font.family: theme.ui
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
            }
        }
    }
}
