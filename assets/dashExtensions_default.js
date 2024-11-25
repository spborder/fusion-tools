window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, ctx) {
            ctx.map.removeLayer(this)
        }
    }
});