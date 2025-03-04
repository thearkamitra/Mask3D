import os
import re
import csv
import json
from pathlib import Path
from hashlib import md5
from natsort import natsorted
import pdb
import numpy as np
from fire import Fire
from tqdm import tqdm
from loguru import logger

from base_preprocessing import BasePreprocessing
import open3d as o3d


def load_obj_with_normals(filepath):
    mesh = o3d.io.read_triangle_mesh(str(filepath))
    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()
    coords = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    colors = np.asarray(mesh.vertex_colors)
    feats = np.hstack((colors, normals))

    return coords, feats


class RioPreprocessing(BasePreprocessing):
    def __init__(
        self,
        data_dir: str = "../3RScan/data/3RScan",
        save_dir: str = "../data_3RScan/processed",
        modes: tuple = ("train", "validation", "test"),
        n_jobs: int = -1,
        git_repo: str = "../3RScan/",
        label_db: str = "./label_database.yaml",
    ):
        super().__init__(data_dir, save_dir, modes, n_jobs)

        git_repo = Path(git_repo)
        self.files = {}
        for mode in self.modes:
            mode = "val" if mode == "validation" else mode
            trainval_split_dir = git_repo / "tot_splits"
            with open(Path(trainval_split_dir) / ("single_" + mode + ".txt")) as f:
                # -1 because the last one is always empty
                split_file = f.read().split("\n")[:-1]

            filepaths = []
            for folder in split_file:
                if os.path.exists(self.data_dir / folder / "mesh.refined.v2.obj"):
                    filepaths.append(self.data_dir / folder / "mesh.refined.v2.obj")
                elif os.path.exists(self.data_dir / folder / "mesh.refined.obj"):
                    filepaths.append(self.data_dir / folder / "mesh.refined.obj")
                else:
                    continue
            mode = "validation" if mode == "val" else mode
            self.files[mode] = natsorted(filepaths)
        self.scannet_label_to_idx = {}
        self.rio_to_scannet_label = {}
        with open(git_repo / "data" / "mapping.tsv") as f:
            reader = csv.reader(f, delimiter="\t")
            columns = next(reader)
            raw_category = columns.index("Label")
            nyu40class = columns.index("NYU40 Mapping")
            nyu40_label = nyu40class - 1
            for row in reader:
                self.rio_to_scannet_label[row[raw_category]] = row[nyu40class]
                self.scannet_label_to_idx[row[nyu40class]] = row[nyu40_label]
        # self.label_db = self._load_yaml(Path(label_db))

    def process_file(self, filepath, mode):
        """process_file.

        Please note, that for obtaining segmentation labels json files were used.

        Args:
            filepath: path to the main ply file
            mode: train, test or validation

        Returns:
            filebase: info about file
        """
        scene_id = filepath.parent.name
        filebase = {
            "filepath": "",
            "raw_filepath": str(filepath),
            "file_len": -1,
        }

        # reading both files and checking that they are fitting
        coords, features = load_obj_with_normals(filepath)
        file_len = len(coords)
        filebase["file_len"] = file_len
        points = np.hstack((coords, features))
        if mode in ["train", "validation"]:
            # getting instance info
            instance_info_filepath = filepath.parent / "semseg.v2.json"
            segment_indexes_filepath = next(filepath.parent.glob("*.segs.v2.json"))
            instance_db = self._read_json(instance_info_filepath)
            segments = self._read_json(segment_indexes_filepath)
            segments = np.array(segments["segIndices"])
            filebase["raw_instance_filepath"] = instance_info_filepath
            filebase["raw_segmentation_filepath"] = segment_indexes_filepath

            segment_ids = np.unique(segments, return_inverse=True)[1]
            points = np.hstack((points, segment_ids[..., None]))
            # adding instance label
            labels = np.full((points.shape[0], 2), -1)
            for instance in instance_db["segGroups"]:
                segments_occupied = np.array(instance["segments"])
                occupied_indices = np.isin(segments, segments_occupied)
                labels[occupied_indices, 1] = instance["id"]
                scannet_label = self.rio_to_scannet_label.get(instance["label"], -1)
                labels[occupied_indices, 0] = self.scannet_label_to_idx[scannet_label]

            points = np.hstack((points, labels))
            gt_data = points[:, -2] * 1000 + points[:, -1] + 1
        else:
            segment_indexes_filepath = next(filepath.parent.glob("*.segs.v2.json"))
            segments = self._read_json(segment_indexes_filepath)
            segments = np.array(segments["segIndices"])
            segment_ids = np.unique(segments, return_inverse=True)[1]
            points = np.hstack((points, segment_ids[..., None]))
            filebase["raw_segmentation_filepath"] = segment_indexes_filepath

        # pdb.set_trace()
        processed_filepath = self.save_dir / mode / f"{scene_id}.npy"
        if not processed_filepath.parent.exists():
            processed_filepath.parent.mkdir(parents=True, exist_ok=True)
        np.save(processed_filepath, points.astype(np.float32))
        filebase["filepath"] = str(processed_filepath)
        if mode == "test":
            return filebase
        processed_gt_filepath = self.save_dir / "instance_gt" / mode / f"{scene_id}.txt"
        if not processed_gt_filepath.parent.exists():
            processed_gt_filepath.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(processed_gt_filepath, gt_data.astype(np.int32), fmt="%d")
        filebase["instance_gt_filepath"] = str(processed_gt_filepath)

        return filebase

    def _read_json(self, path):
        try:
            with open(path) as f:
                file = json.load(f)
        except json.decoder.JSONDecodeError:
            with open(path) as f:
                # in some files I have wrong escapechars as "\o", while it should be "\\o"
                file = json.loads(f.read().replace(r"\o", r"\\o"))
        return file


if __name__ == "__main__":
    Fire(RioPreprocessing)
