#
#
# Author : fcbruce <fcbruce8964@gmail.com>
#
# Time : Sat 29 Sep 2018 15:05:59
#
#
import xgboost as xgb
import lightgbm as lgb
import numpy as np
from sklearn.metrics import roc_auc_score
import os.path as osp
import json
import shutil
import os

class XGBWatcher(object):

    def __init__(self, sig, watchlist=(), dtrain=None):

        self.sig = sig
        self.watchlist = watchlist
        self.dtrain = dtrain
        self.preds = [ None ] * len(watchlist)

    def update(self, r, alpha, bst, dtrain_preds=None):

        displays = []

        for i, watch in enumerate(self.watchlist):

            d, tag = watch
            if d is self.dtrain:
                pred = dtrain_preds
            else:
                pred = self.sig(bst.predict(d))

            pred = pred * alpha

            last_pred = self.preds[i]

            self.preds[i] = pred if last_pred is None else last_pred + pred 

            err = ((self.preds[i] > 0) != d.get_label()).mean()
            auc = roc_auc_score(d.get_label(), self.preds[i])

            text = '{}-err: {:6f}, {}-auc: {:6f}'.format(tag, err, tag, auc)
            displays.append(text)

        print('[{}]\t{}'.format(r, '\t'.join(displays)))
        



class AdaBoost(object):

    def __init__(self, dtype=None, sig=lambda x: (x > 0.5) * 2 - 1):
        
        self.gs = []
        self.dtype = dtype
        self.sig = sig

    def add(self, alpha, g):
        
        self.gs.append((alpha, g))

    def predict(self, data):

        if not isinstance(data, self.dtype):
            raise TypeError('data should be {}, but {} found'.format(self.dtype, type(data)))

        prediction = None
        for alpha, g in self.gs:
            pred = self.sig(g.predict(data)) * alpha
            prediction = pred if prediction is None else prediction + pred

        return prediction

    def load(self, dirname):

        with open(osp.join(dirname, 'adaboost.json'), 'r') as f:
            cfg = json.load(f)
            tag = cfg['tag']
            gs = cfg['alphas']
            if tag == 'xgboost':
                self.dtype = xgb.DMatrix
            else:
                raise TypeError('this type {} is not supported to be loaded'.format(tag))

        self.gs = []

        for g in gs:
            alpha = g['alpha']
            file_path = g['file_path']

            if tag == 'xgboost':
                bst = xgb.Booster(model_file=osp.join(dirname, file_path))

            self.gs.append((alpha, bst))



    def save(self, dirname):

        if osp.isdir(dirname): 
            shutil.rmtree(dirname)
        elif osp.exists(dirname):
            os.remove(dirname)

        os.mkdir(dirname)

        alphas = []
        for i, g in enumerate(self.gs):
            file_path = '{}.model'.format(i)
            alpha, bst = g
            bst.save_model(osp.join(dirname, file_path))
            alphas.append({'alpha': alpha, 'file_path': file_path})

        with open(osp.join(dirname, 'adaboost.json'), 'w') as f:
            if self.dtype is xgb.DMatrix:
                tag = 'xgboost'
            else:
                raise TypeError('this type {} is not supported to be saved'.format(self.dtype))

            cfg = {
                    'tag': tag,
                    'alphas': alphas
                    }

            json.dump(cfg, f)




def __init_weights(n):

    return np.ones(n) 

def __update_weights(w, prediction, groundtruth):
    e = ((prediction != groundtruth) * w).sum() / w.sum()
    alpha = np.log((1 - e) / e) / 2
    w = np.exp(-alpha * (prediction * groundtruth)) * w
    return alpha, w 


def train_xgb(ada_round, xgb_params, dtrain, xgb_num_round, watchlist=(), sig=lambda x: (x > 0.5) * 2 - 1):
    n = dtrain.num_row()
    groundtruth = dtrain.get_label() * 2 - 1
    prediction = None
    ada = AdaBoost(xgb.DMatrix, sig)
    w =  __init_weights(n) 
    watcher = XGBWatcher(sig, watchlist, dtrain)

    for i in range(ada_round):
        dtrain.set_weight(w)
        xgb_params['seed'] = i
        bst = xgb.train(xgb_params, dtrain, xgb_num_round)
        prediction = bst.predict(dtrain)
        prediction = sig(prediction)
        bst = xgb.Booster(model_file=bst.save_raw())
        alpha, w = __update_weights(w, prediction, groundtruth)
        ada.add(alpha, bst)
        watcher.update(i, alpha, bst, prediction)

    return ada


if __name__ == '__main__':
    w = __init_weights(10)
    groundtruth = np.array([1, 1, 1, -1, -1, -1, 1, 1, 1, -1])
    prediction = np.array([1, 1, 1, -1, -1, -1, -1, -1, -1, -1])
    alpha, w = __update_weights(w, prediction, groundtruth)
    print(alpha)
    print(w)
