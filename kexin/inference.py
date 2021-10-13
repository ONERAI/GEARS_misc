import torch
import numpy as np

from sklearn.metrics import r2_score
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import mean_squared_error as mse
from sklearn.metrics import mean_absolute_error as mae

def evaluate(loader, graph, weights, model, args, num_de_idx=20, gene_idx=None):
    """
    Run model in inference mode using a given data loader
    """

    model.eval()
    pert_cat = []
    pred = []
    truth = []
    pred_de = []
    truth_de = []
    results = {}

    for batch in loader:
        batch.to(args['device'])
        model.to(args['device'])
        graph = graph.to(args['device'])
        if weights is not None:
            weights = weights.to(args['device'])
            
        results = {}
        pert_cat.extend(batch.pert)

        with torch.no_grad():

            p = model(batch, graph, weights)
            t = batch.y

            if gene_idx is not None:
                if not args['single_out']:
                    p = p[:,gene_idx]
                t = t[:,gene_idx]

            pred.extend(p.cpu())
            truth.extend(t.cpu())

            # Differentially expressed genes
            if gene_idx is None:
                for itr, de_idx in enumerate(batch.de_idx):
                    if de_idx is not None:
                        pred_de.append(p[itr, de_idx])
                        truth_de.append(t[itr, de_idx])

                    else:
                        pred_de.append([torch.zeros(num_de_idx).to(args['device'])])
                        truth_de.append([torch.zeros(num_de_idx).to(args['device'])])

    # all genes
    results['pert_cat'] = np.array(pert_cat)

    pred = torch.stack(pred)
    truth = torch.stack(truth)
    results['pred']= pred.detach().cpu().numpy()
    results['truth']= truth.detach().cpu().numpy()

    if gene_idx is None:
        pred_de = torch.stack(pred_de)
        truth_de = torch.stack(truth_de)
        results['pred_de']= pred_de.detach().cpu().numpy()
        results['truth_de']= truth_de.detach().cpu().numpy()
    else:
        results['pred_de'] = pred_de
        results['truth_de'] = truth_de

    return results


def compute_metrics(results, gene_idx=None):
    """
    Given results from a model run and the ground truth, compute metrics

    """
    metrics = {}
    metrics_pert = {}

    metric2fct = {
           'mse': mse,
           'mae': mae,
           'spearman': spearmanr,
           'pearson': pearsonr,
           'r2': r2_score
    }
    
    ## macro
    for m, fct in metric2fct.items():
        if m in ['spearman', 'pearson']:
            val = fct(results['pred'].reshape(-1,), results['truth'].reshape(-1,))[0]
            val_de = fct(results['pred_de'].reshape(-1,), results['truth_de'].reshape(-1,))[0]
            if np.isnan(val):
                val = 0
            if np.isnan(val_de):
                val_de = 0
        else:
            val = fct(results['pred'].reshape(-1,), results['truth'].reshape(-1,))
            val_de = fct(results['pred_de'].reshape(-1,), results['truth_de'].reshape(-1,))
        metrics[m + '_macro'] = val
        metrics[m + '_de_macro'] = val_de
        
    
    for m in metric2fct.keys():
        metrics[m] = []
        metrics[m + '_de'] = []

    for pert in np.unique(results['pert_cat']):

        metrics_pert[pert] = {}
        p_idx = np.where(results['pert_cat'] == pert)[0]
        if gene_idx is None:
            
            for m, fct in metric2fct.items():
                if m in ['spearman', 'pearson']:
                    val = fct(results['pred'][p_idx].mean(0), results['truth'][p_idx].mean(0))[0]
                    if np.isnan(val):
                        val = 0
                else:
                    val = fct(results['pred'][p_idx].mean(0), results['truth'][p_idx].mean(0))
                    
                metrics_pert[pert][m] = val
                metrics[m].append(metrics_pert[pert][m])
            
        else:
            for m, fct in metric2fct.items():
                metrics[m].append(0)     
       
        if pert != 'ctrl' and gene_idx is None:
            
            for m, fct in metric2fct.items():
                if m in ['spearman', 'pearson']:
                    val = fct(results['pred_de'][p_idx].mean(0), results['truth_de'][p_idx].mean(0))[0]
                    if np.isnan(val):
                        #print(pert)
                        #print(results['pred_de'][p_idx].mean(0))
                        #print(results['truth_de'][p_idx].mean(0))
                        val = 0
                else:
                    val = fct(results['pred_de'][p_idx].mean(0), results['truth_de'][p_idx].mean(0))
                    
                metrics_pert[pert][m + '_de'] = val
                metrics[m + '_de'].append(metrics_pert[pert][m + '_de'])

        else:
            for m, fct in metric2fct.items():
                metrics_pert[pert][m + '_de'] = 0
    
    for m in metric2fct.keys():
        
        metrics[m] = np.mean(metrics[m])
        metrics[m + '_de'] = np.mean(metrics[m + '_de'])

    return metrics, metrics_pert


def node_specific_batch_out(models, batch):
    # Returns output for all node specific models as a matrix of dimension batch_size x nodes
    outs = []
    for idx in range(len(models)):
        outs.append(models[idx](batch).detach().cpu().numpy()[:,idx])
    return np.vstack(outs).T

# Run prediction over all batches
def batch_predict(loader, loaded_models, args):
    # Prediction for node specific GNNs
    preds = []
    print("Loader size: ", len(loader))
    for itr, batch in enumerate(loader):
        print(itr)
        batch = batch.to(args['device'])
        preds.append(node_specific_batch_out(loaded_models, batch))

    preds = np.vstack(preds)
    return preds


# Read in model for each gene


