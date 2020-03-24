# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/70_callback.wandb.ipynb (unless otherwise specified).

__all__ = ['WandbCallback', 'wandb_process']

# Cell
from ..basics import *
from .progress import *
from ..text.data import TensorText

# Cell
import wandb

# Cell
class WandbCallback(Callback):
    "Saves model topology, losses & metrics"
    toward_end,remove_on_fetch,run_after = True,True,FetchPreds
    # Record if watch has been called previously (even in another instance)
    _wandb_watch_called = False

    def __init__(self, log="gradients", log_preds=True, valid_dl=None, n_preds=36, seed=12345):
        # W&B log step (number of training updates)
        self._wandb_step = 0
        self._wandb_epoch = 0
        # Check if wandb.init has been called
        if wandb.run is None:
            raise ValueError('You must call wandb.init() before WandbCallback()')
        store_attr(self, 'log,log_preds,valid_dl,n_preds,seed')

    def begin_fit(self):
        "Call watch method to log model topology, gradients & weights"
        self.run = not hasattr(self.learn, 'lr_finder') and not hasattr(self, "gather_preds") and rank_distrib()==0
        if not self.run: return
        if not WandbCallback._wandb_watch_called:
            WandbCallback._wandb_watch_called = True
            # Logs model topology and optionally gradients and weights
            wandb.watch(self.learn.model, log=self.log)

        if hasattr(self, 'save_model'): self.save_model.add_save = Path(wandb.run.dir)/'bestmodel.pth'

        if self.log_preds and not self.valid_dl:
            #Initializes the batch watched
            wandbRandom = random.Random(self.seed)  # For repeatability
            self.n_preds = min(self.n_preds, len(self.dls.valid_ds))
            idxs = wandbRandom.sample(range(len(self.dls.valid_ds)), self.n_preds)
            test_items = [self.dls.valid_ds.items[i] for i in idxs]
            self.valid_dl = self.dls.test_dl(test_items, with_labels=True)

        if self.valid_dl:
            self.learn.add_cb(FetchPredsCallback(dl=self.valid_dl, with_input=True, with_decoded=True))

    def after_batch(self):
        "Log hyper-parameters and training loss"
        if self.training:
            self._wandb_step += 1
            self._wandb_epoch += 1/self.n_iter
            hypers = {f'{k}_{i}':v for i,h in enumerate(self.opt.hypers) for k,v in h.items()}
            wandb.log({'epoch': self._wandb_epoch,'train_loss': self.smooth_loss, **hypers}, step=self._wandb_step)

    def after_epoch(self):
        "Log validation loss and custom metrics & log prediction samples"
        # Correct any epoch rounding error and overwrite value
        self._wandb_epoch = round(self._wandb_epoch)
        wandb.log({'epoch': self._wandb_epoch}, step=self._wandb_step)
        # Log sample predictions
        if self.log_preds:
            inp,preds,targs,out = self.learn.fetch_preds.preds
            b = tuplify(inp) + tuplify(targs)
            x,y,its,outs = self.valid_dl.show_results(b, out, show=False, max_n=self.n_preds)
            wandb.log(wandb_process(x, y, its, outs), step=self._wandb_step)
        wandb.log({n:s for n,s in zip(self.recorder.metric_names, self.recorder.log) if n not in ['train_loss', 'epoch', 'time']}, step=self._wandb_step)

    def after_fit(self):
        self.run = True
        if self.log_preds: self.remove_cb(self.learn.fetch_preds)
        wandb.log({}) #To trigger one last synch

# Cell
@typedispatch
def wandb_process(x:TensorImage, y, samples, outs):
    "Process `sample` and `out` depending on the type of `x/y`"
    res = []
    for s,o in zip(samples, outs):
        img = s[0].permute(1,2,0)
        res.append(wandb.Image(img, caption='Input data', grouping=3))
        for t, capt in ((o[0], "Prediction"), (s[1], "Ground Truth")):
            # Resize plot to image resolution (from https://stackoverflow.com/a/13714915)
            my_dpi = 100
            fig = plt.figure(frameon=False, dpi=my_dpi)
            h, w = img.shape[:2]
            fig.set_size_inches(w / my_dpi, h / my_dpi)
            ax = plt.Axes(fig, [0., 0., 1., 1.])
            ax.set_axis_off()
            fig.add_axes(ax)
            # Superimpose label or prediction to input image
            ax = img.show(ctx=ax)
            ax = t.show(ctx=ax)
            res.append(wandb.Image(fig, caption=capt))
            plt.close(fig)
    return {"Prediction Samples": res}

# Cell
@typedispatch
def wandb_process(x:TensorImage, y:(TensorCategory,TensorMultiCategory), samples, outs):
    return {"Prediction Samples": [wandb.Image(s[0].permute(1,2,0), caption=f'Ground Truth: {s[1]}\nPrediction: {o[0]}')
            for s,o in zip(samples,outs)]}

# Cell
@typedispatch
def wandb_process(x:TensorText, y:(TensorCategory,TensorMultiCategory), samples, outs):
    data = [[s[0], s[1], o[0]] for s,o in zip(samples,outs)]
    return {"Prediction Samples": wandb.Table(data=data, columns=["Text", "Target", "Prediction"])}