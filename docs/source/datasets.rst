FUSION Dataset Classes
======================

An auxillary addition to the *fusion-tools* package is the deployment of dataset classes which enable iteration of annotated structures or regions of images for training segmentation or classification problems.


In the below example, an example segmentation and classification dataset are created using some test data

.. code-block:: python

    """Testing out different dataset classes
    """

    import os
    import sys
    sys.path.append('./src/')
    from time import sleep

    import large_image
    import numpy as np
    from fusion_tools.dataset import SegmentationDataset, ClassificationDataset
    from fusion_tools.utils.shapes import load_aperio
    import matplotlib.pyplot as plt

    def main():
        
        test_slide_path = "/path/to/test_slide.svs"
        slide_list = [
            test_slide_path
        ]
        annotations_list = [
            load_aperio(test_slide_path.replace('svs','xml'))    
        ]

        # Default parameters
        seg_dataset = SegmentationDataset(
            slides = slide_list,
            annotations = annotations_list,
            patch_size = [512,512],
            patch_mode = 'centered_bbox'
        )

        # Printing key_configs
        print(seg_dataset)
        print(f'len(seg_dataset): {len(seg_dataset)}')

        # Viewing some image/mask combos:
        for i in range(len(seg_dataset)):
            image, mask = seg_dataset[i]

            plt.imshow(image)
            plt.show(block=False)
            plt.pause(0.25)
            plt.close('all')

            # Normalizing masks (channel = class)
            mask = np.sum(mask,axis=-1)
            plt.imshow(255*mask)
            plt.show(block=False)
            plt.pause(0.25)
            plt.close('all')


        class_dataset = ClassificationDataset(
            slides = slide_list,
            annotations=annotations_list,
            label_property = 'name'
        )

        print(class_dataset)
        print(f'len of class_dataset: {len(class_dataset)}')

        for i in range(len(class_dataset)):
            image,label = class_dataset[i]

            print(f'label: {label}')
            plt.imshow(image)
            plt.show(block=False)
            plt.pause(0.5)
            plt.close('all')

    if __name__=='__main__':
        main()


.. automodule:: fusion_tools.dataset
    :members:












