import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="fusion-tools",
    version="2.0.6",
    author="Sam Border",
    author_email="sam.border2256@gmail.com",
    description="Modular visualization and analysis dashboard creation for high-resolution microscopy images",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/spborder/fusion-tools",
    install_requires=[
        "lxml>=4.9.2",
        "geojson>=3.0.1",
        "shapely>=2.0.1",
        "geopandas",
        "girder-client",
        "numpy>=1.20.0",
        "large-image[common]",
        "wsi-annotations-kit",
        "dash-leaflet[all]>=1.0.15",
        "dash-extensions",
        "dash-bootstrap-components",
        "dash-mantine-components>=0.14.4",
        "dash-treeview-antd",
        "requests",
        "uuid",
        "scikit-image",
        "umap-learn",
        "fastapi>=0.103.2",
        "uvicorn",
        "statsmodels",
        "typing-extensions>=4.8.0"
    ],
    packages=setuptools.find_packages(where = 'src',include=["fusion_tools*"]),
    package_dir={"":"src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)