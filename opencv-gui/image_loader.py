"""Load the imput images to the opencv gui""" 

import os
from typing import List, Dict, Tuple, Optional
import logging
import json

from numpy.typing import NDArray
import cv2

from helpers import get_logger


class ImageLoader:
    def __init__(self, *,
                 directory: str = None,
                 images: List[str] = None,
                 video: str = None,
                 log_level = logging.ERROR,
                 metadata_directory: str = None) -> None:
        """Init ImageLoader

        Args:
            directory (str, optional): path to input directory containing
            the input images. Defaults to None.
            images (List[str], optional): List of image paths. Defaults to None.
            video (str, optional): Path to video to be decomposed into
            images. Defaults to None.
        """
        self.logger = get_logger(name=__name__ + "." + self.__class__.__name__,
                            level=log_level)
        if sum([arg is None for arg in [directory, images, video]]) != 1:
            raise ValueError("Exactly one of the following arguments must be provided: ",
                             " 'directory', 'images', 'video'")

        self.current_image_id = 0

        if directory is not None:
            self.images_paths = list(filter(lambda f: os.path.isfile(f), os.listdir(directory)))
            if metadata_directory is not None:
                self.metadata_directory = metadata_directory
            else:
                self.metadata_directory = directory

        elif images is not None:
            raise NotImplementedError("ImageLoader from 'images' argument is not yet implemented.")

        elif video is not None:
            raise NotImplementedError("ImageLoader from 'video' argument is not yet implemented.")

    def get_current(self) -> Tuple[int, NDArray, str]:
        """Return current image id, image, image path and path to metadata file. If
        the metadata file does not exist the path where the file should be created is
        still returned."""
        image_path = self.images_paths[self.current_image_id]
        image_extension = image_path.split('.')[-1]
        metadata_path = os.path.join(self.metadata_directory,
                                     os.path.basename(image_path).replace(image_extension, "json"))
        return (self.current_image_id,
                cv2.imread(),
                self.images_paths[self.current_image_id],
                metadata_path)

    def next(self, ret_val = False) -> Optional[Tuple[int, NDArray]]:
        """Return next image id and image if not at the final index yet. Else return the current"""
        # increment index with boundary check
        if self.current_image_id < len(self.images_paths) - 1:
            self.current_image_id += 1
        if ret_val:
            # return the current image
            return self.get_current()

    def previous(self, ret_val = False) -> Optional[Tuple[int, NDArray]]:
        """Return previous image id and image if not at the first index yet. Else return the current"""
        # increment index with boundary check
        if self.current_image_id > 0:
            self.current_image_id -= 1
        if ret_val:
            # return the current image
            return self.get_current()