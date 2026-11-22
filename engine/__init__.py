# FlowStudio Core Engine
try:
    from engine.watermark_remover import WatermarkRemover
    if not hasattr(WatermarkRemover, 'masks'):
        WatermarkRemover.masks = property(lambda self: getattr(self, 'master_masks', {}))
except Exception:
    pass

