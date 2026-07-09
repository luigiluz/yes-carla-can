import os
import weakref

import numpy as np
import pygame
import carla


class RGBCameraSensor(object):
    """
    Dedicated front-facing RGB camera sensor.

    Stores the latest frame both as a pygame Surface (for on-screen display)
    and as a raw numpy array (for data export / ML pipelines).

    ── How to access the camera data ──────────────────────────────────────────

    From anywhere that holds a reference to this sensor object:

        # Latest frame as a numpy uint8 array shaped (H, W, 3) in RGB order
        frame_rgb = world.rgb_camera_sensor.array

        # Save the current frame to a PNG file (requires Pillow):
        from PIL import Image
        img = Image.fromarray(frame_rgb)
        img.save("frame.png")

        # Or use OpenCV:
        import cv2
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite("frame.png", frame_bgr)

    To export every frame automatically, set ``recording = True`` on the
    sensor instance.  Frames will be saved under the ``_out/camera/``
    directory as ``<frame_number>.png`` via CARLA's built-in save helper:

        world.rgb_camera_sensor.recording = True   # start
        world.rgb_camera_sensor.recording = False  # stop

    ───────────────────────────────────────────────────────────────────────────
    """

    # Resolution of the camera (pixels).  Must match or be smaller than the
    # pygame display so the PiP overlay fits on screen.
    IMAGE_WIDTH = 640
    IMAGE_HEIGHT = 360

    def __init__(self, parent_actor, gamma_correction=2.2):
        self.sensor = None
        self.surface = None          # pygame.Surface, updated each frame
        self.array = None            # numpy (H, W, 3) uint8 RGB, updated each frame
        self.recording = False       # set True to auto-save every frame to disk

        self._parent = parent_actor

        bound_x = 0.5 + self._parent.bounding_box.extent.x
        bound_z = 0.5 + self._parent.bounding_box.extent.z

        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.camera.rgb')
        bp.set_attribute('image_size_x', str(self.IMAGE_WIDTH))
        bp.set_attribute('image_size_y', str(self.IMAGE_HEIGHT))
        bp.set_attribute('fov', '90')
        if bp.has_attribute('gamma'):
            bp.set_attribute('gamma', str(gamma_correction))

        # Mount on the front hood of the vehicle, slightly elevated.
        spawn_transform = carla.Transform(
            carla.Location(x=bound_x + 0.3, z=bound_z + 0.1),
            carla.Rotation(pitch=0.0),
        )

        self.sensor = world.spawn_actor(
            bp,
            spawn_transform,
            attach_to=self._parent,
            attachment_type=carla.AttachmentType.Rigid,
        )

        weak_self = weakref.ref(self)
        self.sensor.listen(
            lambda image: RGBCameraSensor._on_image(weak_self, image)
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, display, pos=(0, 0)):
        """Blit the latest camera frame onto *display* at *pos* (top-left)."""
        if self.surface is not None:
            display.blit(self.surface, pos)

    # ------------------------------------------------------------------
    # Internal callback
    # ------------------------------------------------------------------

    @staticmethod
    def _on_image(weak_self, image):
        self = weak_self()
        if not self:
            return

        # raw_data is a flat BGRA byte buffer; reshape to (H, W, 4).
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = np.reshape(array, (image.height, image.width, 4))

        # Drop alpha channel and convert BGRA → RGB for conventional use.
        array = array[:, :, :3][:, :, ::-1]

        # Store numpy array (RGB, uint8) — use this for data export.
        self.array = array

        # Build pygame surface (expects (W, H) axis order).
        self.surface = pygame.surfarray.make_surface(array.swapaxes(0, 1))

        if self.recording:
            # CARLA saves the raw BGRA image; the frame number is used as
            # the file name.  Files land in ``_out/camera/<frame>.png``.
            os.makedirs('_out/camera', exist_ok=True)
            image.save_to_disk('_out/camera/%08d' % image.frame)
