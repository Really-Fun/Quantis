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
    // Данные ещё грузятся: лента держит место заглушками, а не появляется
    // потом рывком и не сдвигает всё ниже.
    property bool loading: false
    signal picked(var item, int index)
    signal allClicked()

    // Показанная копия модели: меняется, только если данные правда другие.
    // Иначе каждое обновление пересоздавало плитки и обложки моргали.
    property var shown: []
    property string shownKey: ""
    function sync() {
        var items = model || []
        var key = JSON.stringify(items)
        if (key !== shownKey) {
            shownKey = key
            shown = items
        }
    }
    onModelChanged: sync()
    Component.onCompleted: sync()

    Layout.fillWidth: true
    visible: shown.length > 0 || loading
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
    // Заглушки на время загрузки.
    Row {
        visible: ribbon.shown.length === 0
        Layout.fillWidth: true
        Layout.preferredHeight: ribbon.tile + 64
        Layout.leftMargin: theme.gutter
        spacing: 12
        clip: true
        Repeater {
            model: 4
            Column {
                spacing: 10
                Rectangle {
                    width: ribbon.tile; height: ribbon.tile
                    radius: ribbon.round ? width / 2 : 14
                    color: theme.surfaceHigh
                }
                Rectangle { width: ribbon.tile * 0.7; height: 12; radius: 6; color: theme.surface }
                Rectangle { width: ribbon.tile * 0.45; height: 10; radius: 5; color: theme.surface }
            }
        }
        SequentialAnimation on opacity {
            running: ribbon.visible && ribbon.shown.length === 0 && theme.motion
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.45; duration: 700; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.45; to: 1; duration: 700; easing.type: Easing.InOutSine }
        }
    }
    ListView {
        visible: ribbon.shown.length > 0
        // Плавно проявляется, когда пришли данные.
        opacity: visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: theme.medium } }
        Layout.fillWidth: true
        Layout.preferredHeight: ribbon.tile + 64
        orientation: ListView.Horizontal
        spacing: 12
        leftMargin: theme.gutter
        rightMargin: theme.gutter
        clip: true
        boundsBehavior: Flickable.DragOverBounds
        model: ribbon.shown
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
