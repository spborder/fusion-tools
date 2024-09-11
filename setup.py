import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="fusion-tools",
    version="0.0.7",
    author="Sam Border",
    author_email="sam.border2256@gmail.com",
    description="Utility functions for generating, saving, and converting annotation files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/spborder/fusion-tools",
    install_requires=[
        "lxml>=4.9.2",
        "geojson>=3.0.1",
        "shapely>=2.0.1",
        "tqdm",
        "numpy>=1.20.0",
        "large-image[common]",
        "wsi-annotations-kit",
        "dash-leaflet",
        "dash-extensions",
        "dash-bootstrap-components",
        "dash-mantine-components",
        "dash-treeview-antd",
        "requests",
        "uuid",
        "scikit-image",
        "umap-learn",
        "fastapi",
        "uvicorn",
        "threading",
        "sphinx",
        "sphinx-rtd-theme",
        "statsmodels"
    ],
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)